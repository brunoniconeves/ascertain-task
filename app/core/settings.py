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
