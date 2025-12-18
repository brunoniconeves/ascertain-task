from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientNoteCreateJson(BaseModel):
    taken_at: datetime
    note_type: str | None = Field(default=None, max_length=50)
    content_text: str = Field(min_length=1)
    content_mime_type: str | None = Field(default="text/plain", max_length=255)


class StructuredSoapSections(BaseModel):
    """
    Derived SOAP sections extracted from the raw note.

    Values may be missing/None when the parser confidence is partial.
    """

    subjective: str | None = None
    objective: str | None = None
    assessment: str | None = None
    plan: str | None = None


class StructuredNoteData(BaseModel):
    """
    Optional derived structured data linked to a note.

    IMPORTANT (healthcare semantics):
    - This is derived (best-effort) and therefore non-authoritative.
    - The clinical source of truth remains the raw note content (inline text or file).
    - We never infer/generate structured data at read time; this is only returned if persisted.
    """

    # Use an internal name to avoid shadowing BaseModel.schema(), but keep the JSON field
    # name exactly "schema" for API compatibility.
    model_config = ConfigDict(populate_by_name=True)

    schema_: str = Field(
        alias="schema", description="Derived schema identifier, e.g. 'soap_v1'."
    )
    derived: bool = Field(
        default=True,
        description="Always true when present; indicates this data is derived and non-authoritative.",
    )
    sections: StructuredSoapSections


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

    # Optional derived/non-authoritative structured data (never generated at read time).
    structured_data: StructuredNoteData | None = None

    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class PatientNoteListOut(BaseModel):
    """
    Note list response.

    For performance and payload-size reasons, list items expose only a boolean flag
    indicating whether derived structured data exists; callers can fetch the full
    derived payload via GET /patients/{patient_id}/notes/{note_id}.
    """

    class PatientNoteListItemOut(BaseModel):
        model_config = ConfigDict(from_attributes=True)

        # Keep all existing fields from PatientNoteOut for backwards compatibility.
        id: uuid.UUID
        patient_id: uuid.UUID
        taken_at: datetime
        note_type: str | None
        has_file: bool

        content_text: str | None
        content_mime_type: str | None

        file_size_bytes: int | None
        checksum_sha256: str | None

        # Lightweight signal only (derived, non-authoritative, and never computed at read time).
        has_structured_data: bool = False

        created_at: datetime
        updated_at: datetime
        deleted_at: datetime | None

    items: list[PatientNoteListItemOut]
    limit: int
    next_cursor: str | None = None


