"""Subprocess CLI adapter: the retrieval seam runs without Node or network.

The adapter spawns `<node_bin> <cli_path> discover --config .. --input ..
--id .. --output-root ..`, tolerates timeouts, and treats the on-disk
observation.json as authoritative over stdout when both exist (ADR-013).
"""

import asyncio
import json
import textwrap
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
    input_path.write_text(json.dumps({"queries": [{"id": "q-1", "query": "api security"}]}))
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


def test_success_doc_round_trips_from_disk(tmp_path: Path) -> None:
    doc = {
        "schemaVersion": 1,
        "observationId": "attempt-q-1",
        "status": "success",
        "capability": "discovery",
        "providerVariant": "obscura-duckduckgo-lite",
        "configSha256": "0" * 64,
        "startedAt": "2026-08-23T00:00:00Z",
        "completedAt": "2026-08-23T00:00:01Z",
        "evidenceDirectory": str(tmp_path / "evidence" / "attempts" / "attempt-q-1"),
    }
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
    assert result.stderr_tail == ""
    assert result.observation_doc == doc


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

    assert result.observation_doc == disk_doc
    assert result.observation_doc is not None
    assert result.observation_doc["status"] == "no_results"


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
    assert result.observation_doc is None


def test_timeout_kills_process_and_reports(tmp_path: Path) -> None:
    stub = write_stub_node(
        tmp_path,
        body="""
            sleep 30
            exit 0
            """,
    )

    result = invoke(stub, tmp_path, timeout_seconds=1)

    assert result.timed_out is True
    assert result.observation_doc is None
