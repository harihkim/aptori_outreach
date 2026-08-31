from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
REPO_ROOT = BACKEND_ENV_FILE.parents[1]


class Settings(BaseSettings):
    app_name: str = "aptori-outreach-backend"
    database_url: str = "postgresql+psycopg://@/aptori_outreach"
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    # Bearer token guarding the API. Fails closed while unset; an empty
    # string is an unset token, not a token that authenticates nothing.
    api_token: str | None = None

    # Discovery worker wiring. Redis hosts the arq queue; the retrieval CLI
    # runs through the local node binary against the frozen obscura-retrieval
    # package and its prototype-smoke fixtures.
    redis_url: str = "redis://127.0.0.1:6379/0"
    retrieval_node_bin: str = "node"
    retrieval_cli_path: Path = (
        REPO_ROOT / "packages" / "obscura-retrieval" / "bin" / "retrieval-cli.js"
    )
    discovery_provider_config_path: Path = (
        REPO_ROOT
        / "retrieval-eval"
        / "prototype-smoke"
        / "provider-configs"
        / "obscura-duckduckgo-lite.json"
    )
    discovery_query_document_path: Path = (
        REPO_ROOT / "retrieval-eval" / "prototype-smoke" / "queries-2026-08.json"
    )
    # The retrieval process may only write below this expendable tree. Python
    # consumes and removes individual attempts after copying their raw source
    # into the durable content-addressed store below.
    retrieval_staging_root: Path = REPO_ROOT / "retrieval-staging"
    # Durable EvidenceStore root. It is intentionally separate from the
    # retrieval staging tree, including when the two live on different filesystems.
    retrieval_evidence_root: Path = REPO_ROOT / "evidence-runs"
    # Python-owned scratch space for query input documents. The evidence
    # output root belongs to the retrieval CLI (ADR ownership); inputs are
    # staged outside it so the two toolchains never write into each other's
    # trees.
    retrieval_input_scratch_root: Path = REPO_ROOT / "scratch" / "discovery-inputs"
    retrieval_attempt_timeout_seconds: int = Field(default=180, ge=5, le=900)

    # Explicit EvidenceStore safety limits. Keeping these in settings makes
    # deployment policy visible and prevents a caller from widening limits per
    # attempt.
    evidence_store_max_artifacts: int = Field(default=128, ge=1)
    evidence_store_max_artifact_bytes: int = Field(default=128 * 1024 * 1024, ge=1)
    evidence_store_max_total_bytes: int = Field(default=512 * 1024 * 1024, ge=1)
    evidence_store_max_manifest_bytes: int = Field(default=1024 * 1024, ge=1)
    evidence_store_max_name_bytes: int = Field(default=255, ge=1)
    evidence_store_max_role_bytes: int = Field(default=128, ge=1)
    evidence_store_max_media_type_bytes: int = Field(default=255, ge=1)

    model_config = SettingsConfigDict(
        env_prefix="APTORI_",
        env_file=BACKEND_ENV_FILE,
        extra="ignore",
    )

    @field_validator("api_token", mode="before")
    @classmethod
    def _blank_token_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @model_validator(mode="after")
    def _retrieval_roots_are_disjoint(self) -> "Settings":
        """Prevent staging cleanup from ever touching durable evidence."""
        staging = self.retrieval_staging_root.resolve()
        durable = self.retrieval_evidence_root.resolve()
        if staging == durable:
            raise ValueError(
                "retrieval_staging_root and retrieval_evidence_root must be distinct"
            )
        try:
            staging.relative_to(durable)
        except ValueError:
            pass
        else:
            raise ValueError(
                "retrieval_staging_root may not be nested in retrieval_evidence_root"
            )
        try:
            durable.relative_to(staging)
        except ValueError:
            pass
        else:
            raise ValueError(
                "retrieval_evidence_root may not be nested in retrieval_staging_root"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
