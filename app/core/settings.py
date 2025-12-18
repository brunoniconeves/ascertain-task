from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ascertain-task"
    database_url: str = Field(
        description="SQLAlchemy DB URL (e.g. postgresql+asyncpg://user:pass@host:5432/db)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
