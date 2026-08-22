from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "aptori-outreach-backend"
    database_url: str = "postgresql+psycopg://@/aptori_outreach"
    # Bearer token guarding write endpoints. Writes fail closed while unset.
    api_token: str | None = None

    model_config = {"env_prefix": "APTORI_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
