"""Subprocess adapter around the retrieval CLI.

The adapter is the only place that spawns the frozen Node tool. It owns the
process boundary: argument wiring, timeout enforcement, and evidence
resolution.

Disk authority: stdout may tell us WHERE the observation lives
(evidenceDirectory), but only observation.json on disk is ever allowed to
feed the full parser. A stdout projection without a pointer is classified
explicitly (no_evidence_pointer) instead of being trusted, and a pointer to
an unreadable artifact is classified explicitly too (disk_unreadable).

After a timeout kill the adapter attempts deterministic disk recovery of an
observation.json the CLI managed to write before it died; a recovered,
valid document resolves the attempt normally (it is disk evidence like any
other), while failed recovery falls back to the plain timeout classification.
"""

import asyncio
import json
import os
import re
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.discovery.observations import redact_sensitive_text

# Stderr is kept for failure classification but truncated so a chatty
# provider cannot balloon a database row. redact_sensitive_text applies the
# tighter persistence cap before anything reaches the database.
STDERR_TAIL_LIMIT = 4000

# Where the authoritative document came from. Only "disk" ever carries a
# document worth parsing.
EvidenceSource = Literal["disk", "disk_unreadable", "no_evidence_pointer", "none"]


@dataclass(frozen=True)
class CliResult:
    """Outcome of one retrieval CLI attempt."""

    exit_code: int
    stderr_tail: str
    timed_out: bool
    evidence_source: EvidenceSource = "none"
    observation_doc: dict[str, Any] | None = None


def _read_disk_observation(evidence_directory: str) -> tuple[EvidenceSource, dict[str, Any] | None]:
    """Read the authoritative observation.json below the evidence directory."""
    disk_path = Path(evidence_directory) / "observation.json"
    try:
        parsed = json.loads(disk_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return "disk_unreadable", None
    if isinstance(parsed, dict):
        return "disk", parsed
    return "disk_unreadable", None


def _resolve_authoritative_document(
    stdout_text: str,
) -> tuple[EvidenceSource, dict[str, Any] | None]:
    """Locate the authoritative document via stdout; never trust its content."""
    try:
        parsed = json.loads(stdout_text)
    except json.JSONDecodeError:
        return "none", None
    if not isinstance(parsed, dict):
        return "none", None

    evidence_directory = parsed.get("evidenceDirectory")
    if not isinstance(evidence_directory, str) or not evidence_directory:
        # Stdout carried no pointer to disk evidence. Its own content must
        # never stand in for the authoritative artifact.
        return "no_evidence_pointer", None
    return _read_disk_observation(evidence_directory)


def _mtime_ns(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _safe_name(value: str) -> str:
    """Mirror packages/obscura-retrieval/src/evidence.js safeName."""
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value))
    sanitized = sanitized.strip("-")[:80]
    return sanitized or "attempt"


def _recover_timed_out_document(output_root: Path, query_id: str) -> dict[str, Any] | None:
    """Deterministic disk recovery after a timeout kill.

    Preference order: attempt directories whose name starts with
    ``safeName(query_id) + '_'`` first (matching the real evidence.js layout
    ``<capability>/<safeName(logicalId)>_<timestamp>_<rand>/``), then any
    other observation.json under the evidence root, newest mtime first with
    lexicographic path as the tie-break. The first candidate that parses to a
    JSON object wins.
    """
    if not output_root.exists():
        return None
    try:
        candidates = [
            path for path in output_root.rglob("observation.json") if path.is_file()
        ]
    except OSError:
        return None

    prefix = f"{_safe_name(query_id)}_"

    def recovery_sort_key(path: Path) -> tuple[bool, int, str]:
        return (
            not path.parent.name.startswith(prefix),
            -_mtime_ns(path),
            str(path),
        )

    candidates.sort(key=recovery_sort_key)
    for path in candidates:
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


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
    recovered_document: dict[str, Any] | None = None
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        timed_out = True
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        stdout_bytes, stderr_bytes = await process.communicate()
        # The CLI may have finished writing its evidence before it died;
        # disk recovery turns a killed attempt into a completed one.
        recovered_document = _recover_timed_out_document(Path(output_root), query_id)
    except BaseException:
        # arq enforces job_timeout by cancelling the task (CancelledError).
        # Always kill the detached process group before propagating so the
        # start_new_session child tree does not leak.
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            await process.communicate()
        except BaseException:
            pass
        raise

    stderr_tail = redact_sensitive_text(
        stderr_bytes.decode("utf-8", errors="replace")[-STDERR_TAIL_LIMIT:]
    )

    if timed_out and recovered_document is not None:
        # Resolved by authoritative disk evidence despite the kill.
        return CliResult(
            exit_code=process.returncode if process.returncode is not None else -1,
            stderr_tail=stderr_tail,
            timed_out=False,
            evidence_source="disk",
            observation_doc=recovered_document,
        )

    evidence_source: EvidenceSource = "none"
    observation_doc: dict[str, Any] | None = None
    if not timed_out:
        evidence_source, observation_doc = _resolve_authoritative_document(
            stdout_bytes.decode("utf-8", errors="replace")
        )

    return CliResult(
        exit_code=process.returncode if process.returncode is not None else -1,
        stderr_tail=stderr_tail,
        timed_out=timed_out,
        evidence_source=evidence_source,
        observation_doc=observation_doc,
    )
