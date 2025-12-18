from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientNoteCreateJson(BaseModel):
    taken_at: datetime
    note_type: str | None = Field(default=None, max_length=50)
    content_text: str = Field(min_length=1)
    content_mime_type: str | None = Field(default="text/plain", max_length=255)


class PatientNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    taken_at: datetime
    note_type: str | None
    has_file: bool

    content_text: str | None
    content_mime_type: str | None

    file_size_bytes: int | None
    checksum_sha256: str | None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class PatientNoteListOut(BaseModel):
    items: list[PatientNoteOut]
    limit: int
    next_cursor: str | None = None


