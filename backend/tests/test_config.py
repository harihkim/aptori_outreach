"""Focused configuration validation tests that do not require PostgreSQL."""

from pathlib import Path

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("staging", "durable"),
    [
        ("/tmp/evidence", "/tmp/evidence"),
        ("/tmp/evidence/staging", "/tmp/evidence"),
        ("/tmp/evidence", "/tmp/evidence/durable"),
    ],
)
def test_retrieval_roots_must_be_disjoint(staging: str, durable: str) -> None:
    with pytest.raises(ValueError, match="retrieval_.*root"):
        Settings(
            _env_file=None,
            retrieval_staging_root=Path(staging),
            retrieval_evidence_root=Path(durable),
        )


def test_retrieval_roots_allow_unrelated_nonexistent_paths(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        retrieval_staging_root=tmp_path / "not-yet-created" / "staging",
        retrieval_evidence_root=tmp_path / "not-yet-created" / "durable",
    )
    assert settings.retrieval_staging_root != settings.retrieval_evidence_root
