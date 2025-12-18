from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
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

    # Local patient-note storage (filesystem)
    file_storage_backend: str = Field(
        default="local",
        validation_alias=AliasChoices("FILE_STORAGE_BACKEND", "file_storage_backend"),
        description="File storage backend for notes (default: local).",
    )
    local_storage_base_path: str = Field(
        default="./data/notes",
        validation_alias=AliasChoices("LOCAL_STORAGE_BASE_PATH", "NOTES_BASE_DIR", "local_storage_base_path"),
        description="Base directory where file-based patient notes are stored (relative or absolute).",
    )
    max_note_upload_mb: int = Field(
        default=5,
        ge=1,
        validation_alias=AliasChoices("MAX_NOTE_UPLOAD_MB", "max_note_upload_mb"),
        description="Maximum allowed upload size for note files (MB).",
    )
    notes_allowed_mime_types: list[str] = Field(
        default_factory=lambda: [
            "text/plain",
            "application/pdf",
            "image/png",
            "image/jpeg",
        ],
        validation_alias=AliasChoices("NOTES_ALLOWED_MIME_TYPES", "notes_allowed_mime_types"),
        description="Allowlist of MIME types accepted for note uploads.",
    )

    # LLM integration (OpenAI)
    # IMPORTANT (healthcare safety): keep configuration explicit and avoid implicit logging.
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
        description="OpenAI API key (required for /patients/{id}/summary).",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "openai_model"),
        description="OpenAI model identifier used for summary generation.",
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "openai_base_url"),
        description="Base URL for OpenAI API (override for proxies/emulators).",
    )
    openai_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        validation_alias=AliasChoices("OPENAI_TIMEOUT_SECONDS", "openai_timeout_seconds"),
        description="Timeout for OpenAI API requests (seconds).",
    )
    openai_max_prompt_chars: int = Field(
        default=60_000,
        ge=1_000,
        validation_alias=AliasChoices("OPENAI_MAX_PROMPT_CHARS", "openai_max_prompt_chars"),
        description="Soft cap for prompt size to reduce risk of overlong requests.",
    )

    @property
    def notes_base_dir(self) -> str:
        # Backwards-compatible alias used by earlier code.
        return self.local_storage_base_path

    @property
    def notes_max_upload_bytes(self) -> int:
        # Backwards-compatible alias used by earlier code.
        return int(self.max_note_upload_mb) * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
