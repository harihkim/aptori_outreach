from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "aptori-outreach-backend"
    database_url: str = "postgresql+psycopg://@/aptori_outreach"
    # Bearer token guarding the API. Fails closed while unset; an empty
    # string is an unset token, not a token that authenticates nothing.
    api_token: str | None = None

    model_config = {"env_prefix": "APTORI_", "env_file": ".env", "extra": "ignore"}

    @field_validator("api_token", mode="before")
    @classmethod
    def _blank_token_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
