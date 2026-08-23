from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
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
    retrieval_evidence_root: Path = REPO_ROOT / "evidence-runs"
    retrieval_attempt_timeout_seconds: int = Field(default=180, ge=5, le=900)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
