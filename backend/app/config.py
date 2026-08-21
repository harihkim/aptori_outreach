from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "aptori-outreach-backend"
    database_url: str = "postgresql+psycopg://@/aptori_outreach"

    model_config = {"env_prefix": "APTORI_", "env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
