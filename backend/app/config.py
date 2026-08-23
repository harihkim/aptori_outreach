from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    app_name: str = "aptori-outreach-backend"
    database_url: str = "postgresql+psycopg://@/aptori_outreach"
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)
    # Bearer token guarding the API. Fails closed while unset; an empty
    # string is an unset token, not a token that authenticates nothing.
    api_token: str | None = None

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
