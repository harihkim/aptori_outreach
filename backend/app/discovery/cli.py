"""Subprocess adapter around the retrieval CLI.

The adapter is the only place that spawns the frozen Node tool. It owns the
process boundary: argument wiring, timeout enforcement, and evidence
resolution. When both stdout and disk carry an observation, disk wins
(ADR-013) because the attempt directory is written transactionally by the
tool while stdout is merely its last word.
"""

import asyncio
import json
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Stderr is kept for failure classification but truncated so a chatty
# provider cannot balloon a database row.
STDERR_TAIL_LIMIT = 4000


@dataclass(frozen=True)
class CliResult:
    """Outcome of one retrieval CLI attempt."""

    exit_code: int
    observation_doc: dict[str, Any] | None
    stderr_tail: str
    timed_out: bool


def _resolve_document(stdout_text: str) -> dict[str, Any] | None:
    """Best-effort observation resolution: stdout first, disk as authority."""
    try:
        parsed = json.loads(stdout_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None

    evidence_directory = parsed.get("evidenceDirectory")
    if isinstance(evidence_directory, str) and evidence_directory:
        disk_path = Path(evidence_directory) / "observation.json"
        try:
            disk_doc = json.loads(disk_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return parsed
        if isinstance(disk_doc, dict):
            return disk_doc
    return parsed


async def run_retrieval_cli(
    command: str,
    *,
    node_bin: str | Path,
    cli_path: str | Path,
    config_path: str | Path,
    input_path: str | Path,
    query_id: str,
    output_root: str | Path,
    timeout_seconds: float,
) -> CliResult:
    """Run one retrieval command to completion (or timeout).

    Raises nothing for provider failures: every outcome short of an internal
    error is reported through the returned CliResult.
    """
    process = await asyncio.create_subprocess_exec(
        str(node_bin),
        str(cli_path),
        command,
        "--config",
        str(config_path),
        "--input",
        str(input_path),
        "--id",
        query_id,
        "--output-root",
        str(output_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Own process group so a timeout can kill the whole tree: Node tools
        # spawn children (browser drivers) that would otherwise inherit the
        # output pipes and stall reaping after the parent dies.
        start_new_session=True,
    )

    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            process.kill()
        stdout_bytes, stderr_bytes = await process.communicate()

    stderr_tail = stderr_bytes.decode("utf-8", errors="replace")[-STDERR_TAIL_LIMIT:]

    observation_doc: dict[str, Any] | None = None
    if not timed_out:
        observation_doc = _resolve_document(
            stdout_bytes.decode("utf-8", errors="replace")
        )

    return CliResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        observation_doc=observation_doc,
        stderr_tail=stderr_tail,
        timed_out=timed_out,
    )
