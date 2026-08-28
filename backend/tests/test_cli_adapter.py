"""Subprocess CLI adapter: the retrieval seam runs without Node or network.

The adapter spawns `<node_bin> <cli_path> discover --config .. --input ..
--id .. --output-root ..`, tolerates timeouts, and treats the on-disk
observation.json as the ONLY authoritative document (ADR-013): stdout may
locate evidence but its content never feeds the parser. After a timeout
kill it attempts deterministic disk recovery of a written observation.
"""

import asyncio
import json
import os
import textwrap
import time
from pathlib import Path

from app.discovery.cli import CliResult, run_retrieval_cli


def write_stub_node(tmp_path: Path, *, body: str) -> Path:
    """Generate a fake node executable implementing the CLI contract."""
    stub = tmp_path / "fake-node.js"
    stub.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            OUT=""
            while [[ $# -gt 0 ]]; do
              case "$1" in
                --output-root) OUT="$2"; shift 2 ;;
                *) shift ;;
              esac
            done
            ATTEMPT_DIR="$OUT/attempts/attempt-q-1"
            mkdir -p "$ATTEMPT_DIR"
            """
        )
        + textwrap.dedent(body)
    )
    stub.chmod(0o755)
    return stub


def write_input_and_config(tmp_path: Path) -> tuple[Path, Path]:
    input_path = tmp_path / "input-q-1.json"
    input_path.write_text(
        json.dumps({"queries": [{"id": "q-1", "query": "api security"}]})
    )
    config_path = tmp_path / "provider-config.json"
    config_path.write_text(json.dumps({"providerVariant": "obscura-duckduckgo-lite"}))
    return input_path, config_path


def invoke(stub: Path, tmp_path: Path, *, timeout_seconds: float = 10) -> CliResult:
    """Run the adapter against the stub with deterministic paths."""
    input_path, config_path = write_input_and_config(tmp_path)
    return asyncio.run(
        run_retrieval_cli(
            "discover",
            node_bin=str(stub),
            cli_path=str(tmp_path / "retrieval-cli.js"),
            config_path=str(config_path),
            input_path=str(input_path),
            query_id="q-1",
            output_root=str(tmp_path / "evidence"),
            timeout_seconds=timeout_seconds,
        )
    )


def full_disk_doc(tmp_path: Path, *, status: str = "success") -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "observationId": "attempt-q-1",
        "status": status,
        "capability": "discovery",
        "providerVariant": "obscura-duckduckgo-lite",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00Z",
        "completedAt": "2026-08-23T00:00:01Z",
        "evidenceDirectory": str(tmp_path / "evidence" / "attempts" / "attempt-q-1"),
    }


def test_success_doc_round_trips_from_disk(tmp_path: Path) -> None:
    doc = full_disk_doc(tmp_path)
    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf '%s' '{json.dumps(doc)}' > "$ATTEMPT_DIR/observation.json"
            cat "$ATTEMPT_DIR/observation.json"
            exit 0
            """,
    )

    result = invoke(stub, tmp_path)

    assert isinstance(result, CliResult)
    assert result.timed_out is False
    assert result.exit_code == 0
    assert result.evidence_source == "disk"
    assert result.observation_doc == doc
    assert result.stderr_tail == ""


def test_disk_observation_is_authoritative_over_stdout(tmp_path: Path) -> None:
    """ADR-013: when stdout and disk disagree, disk wins."""
    stdout_doc = {
        "schemaVersion": 1,
        "status": "success",
        "observationId": "stdout",
        "evidenceDirectory": str(tmp_path / "evidence" / "attempts" / "attempt-q-1"),
    }
    disk_doc = {
        "schemaVersion": 1,
        "status": "no_results",
        "observationId": "disk",
        "candidateCount": 0,
    }
    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf '%s' '{json.dumps(disk_doc)}' > "$ATTEMPT_DIR/observation.json"
            printf '%s' '{json.dumps(stdout_doc)}'
            exit 0
            """,
    )

    result = invoke(stub, tmp_path)

    assert result.evidence_source == "disk"
    assert result.observation_doc == disk_doc
    assert result.observation_doc is not None
    assert result.observation_doc["status"] == "no_results"


def test_stdout_without_pointer_is_never_the_document(tmp_path: Path) -> None:
    """A complete-looking stdout projection without a pointer is unlocated."""
    projection = {
        "schemaVersion": 1,
        "observationId": "attempt-q-1",
        "capability": "discovery",
        "providerVariant": "obscura-duckduckgo-lite",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00Z",
        "completedAt": "2026-08-23T00:00:01Z",
        "status": "success",
    }
    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf '%s' '{json.dumps(projection)}'
            exit 0
            """,
    )

    result = invoke(stub, tmp_path)

    assert result.exit_code == 0
    assert result.evidence_source == "no_evidence_pointer"
    assert result.observation_doc is None


def test_nonzero_exit_with_stderr_yields_no_document(tmp_path: Path) -> None:
    stub = write_stub_node(
        tmp_path,
        body="""
            echo "boom: provider exploded" >&2
            exit 1
            """,
    )

    result = invoke(stub, tmp_path)

    assert result.exit_code == 1
    assert result.timed_out is False
    assert result.evidence_source == "none"
    assert result.observation_doc is None
    assert "boom: provider exploded" in result.stderr_tail


def test_unparseable_stdout_yields_no_document(tmp_path: Path) -> None:
    stub = write_stub_node(
        tmp_path,
        body="""
            printf 'not json at all'
            exit 0
            """,
    )

    result = invoke(stub, tmp_path)

    assert result.exit_code == 0
    assert result.evidence_source == "none"
    assert result.observation_doc is None


def test_unreadable_disk_document_never_trusts_stdout(tmp_path: Path) -> None:
    """Garbage on disk plus a parseable pointer-bearing stdout fails honestly."""
    stdout_doc = {
        "status": "success",
        "observationId": "attempt-q-1",
        "evidenceDirectory": str(tmp_path / "evidence" / "attempts" / "attempt-q-1"),
    }
    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf 'garbage not json' > "$ATTEMPT_DIR/observation.json"
            printf '%s' '{json.dumps(stdout_doc)}'
            exit 0
            """,
    )

    result = invoke(stub, tmp_path)

    assert result.observation_doc is None
    assert result.evidence_source == "disk_unreadable"


def test_timeout_without_written_evidence_reports_timeout(tmp_path: Path) -> None:
    stub = write_stub_node(
        tmp_path,
        body="""
            sleep 30
            exit 0
            """,
    )

    result = invoke(stub, tmp_path, timeout_seconds=1)

    assert result.timed_out is True
    assert result.evidence_source == "none"
    assert result.observation_doc is None


def test_timeout_recovers_already_written_observation_from_disk(tmp_path: Path) -> None:
    doc = full_disk_doc(tmp_path)
    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf '%s' '{json.dumps(doc)}' > "$ATTEMPT_DIR/observation.json"
            sleep 30
            exit 0
            """,
    )

    result = invoke(stub, tmp_path, timeout_seconds=1)

    # The kill happened after the evidence landed; recovery resolves it.
    assert result.timed_out is False
    assert result.evidence_source == "disk"
    assert result.observation_doc == doc


def test_recovery_prefers_this_querys_attempt_directory(tmp_path: Path) -> None:
    """Deterministic recovery: attempt-q-1 wins even with an older mtime."""
    preferred = full_disk_doc(tmp_path)
    other = dict(full_disk_doc(tmp_path, status="no_results"))
    other["observationId"] = "attempt-other"
    other_dir = tmp_path / "evidence" / "attempts" / "attempt-other"
    other_dir.mkdir(parents=True, exist_ok=True)
    (other_dir / "observation.json").write_text(json.dumps(other), encoding="utf-8")

    older = time.time() - 60
    os.utime((other_dir / "observation.json"), (older, older))

    stub = write_stub_node(
        tmp_path,
        body=f"""
            printf '%s' '{json.dumps(preferred)}' > "$ATTEMPT_DIR/observation.json"
            sleep 30
            exit 0
            """,
    )

    result = invoke(stub, tmp_path, timeout_seconds=1)

    assert result.timed_out is False
    assert result.observation_doc == preferred


def test_stderr_tail_is_redacted_before_return(tmp_path: Path) -> None:
    """Secrets and local usernames never survive into persisted stderr."""
    stub = write_stub_node(
        tmp_path,
        body="""
            echo 'GET https://x.test/?jsc_orig_r=supersecret&ok=1 from /home/hari/evidence failed' >&2
            exit 1
            """,
    )

    result = invoke(stub, tmp_path)

    assert "supersecret" not in result.stderr_tail
    assert "jsc_orig_r=<redacted>" in result.stderr_tail
    assert "/home/hari" not in result.stderr_tail
    assert "~/evidence" in result.stderr_tail
    assert "ok=1" in result.stderr_tail  # non-sensitive values stay intact
