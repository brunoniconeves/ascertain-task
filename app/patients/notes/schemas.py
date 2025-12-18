from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PatientNoteCreateJson(BaseModel):
    taken_at: datetime = Field(
        description="When the note was taken (ISO 8601 date-time).",
        examples=["2025-01-01T12:34:56Z"],
    )
    note_type: str | None = Field(
        default=None,
        max_length=50,
        description="Optional note type hint (e.g. `soap`).",
        examples=["soap"],
    )
    content_text: str = Field(
        min_length=1,
        description="Raw note content as inline text. This is the clinical source of truth.",
        examples=["S: ...\nO: ...\nA: ...\nP: ..."],
    )
    content_mime_type: str | None = Field(
        default="text/plain",
        max_length=255,
        description="MIME type for `content_text`. Defaults to `text/plain`.",
        examples=["text/plain"],
    )


class StructuredSoapSections(BaseModel):
    """
    Derived SOAP sections extracted from the raw note.

    Values may be missing/None when the parser confidence is partial.
    """

    subjective: str | None = Field(
        default=None, description="SOAP Subjective section (S). May be null when unavailable."
    )
    objective: str | None = Field(
        default=None, description="SOAP Objective section (O). May be null when unavailable."
    )
    assessment: str | None = Field(
        default=None, description="SOAP Assessment section (A). May be null when unavailable."
    )
    plan: str | None = Field(
        default=None, description="SOAP Plan section (P). May be null when unavailable."
    )


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

    schema_: str = Field(alias="schema", description="Derived schema identifier, e.g. 'soap_v1'.")
    derived: bool = Field(
        default=True,
        description=(
            "Always true when present; indicates this data is derived and non-authoritative."
        ),
    )
    sections: StructuredSoapSections


class PatientNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(description="Note identifier (UUID).")
    patient_id: uuid.UUID = Field(description="Owning patient identifier (UUID).")
    taken_at: datetime = Field(description="When the note was taken (ISO 8601 date-time).")
    note_type: str | None = Field(
        default=None, description="Optional note type hint (e.g. `soap`)."
    )
    has_file: bool = Field(description="True when the note was uploaded as a file.")

    content_text: str | None = Field(
        default=None,
        description="Inline note content (only present when created as JSON).",
    )
    content_mime_type: str | None = Field(
        default=None,
        description="MIME type of inline content or uploaded file (when known).",
        examples=["text/plain"],
    )

    file_size_bytes: int | None = Field(
        default=None, description="Size of uploaded file in bytes (file-backed notes only)."
    )
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256 checksum of uploaded file contents (file-backed notes only).",
        examples=["4d2c2e1b8a..."],
    )

    # Optional derived/non-authoritative structured data (never generated at read time).
    structured_data: StructuredNoteData | None = None

    created_at: datetime = Field(description="Record creation timestamp (UTC).")
    updated_at: datetime = Field(description="Record last update timestamp (UTC).")
    deleted_at: datetime | None = Field(
        default=None,
        description=(
            "Soft-delete timestamp (UTC). When set, note content should be considered removed."
        ),
    )


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
        id: uuid.UUID = Field(description="Note identifier (UUID).")
        patient_id: uuid.UUID = Field(description="Owning patient identifier (UUID).")
        taken_at: datetime = Field(description="When the note was taken (ISO 8601 date-time).")
        note_type: str | None = Field(default=None, description="Optional note type hint.")
        has_file: bool = Field(description="True when the note was uploaded as a file.")

        content_text: str | None = Field(
            default=None, description="Inline note content (present for JSON-created notes)."
        )
        content_mime_type: str | None = Field(
            default=None, description="MIME type of inline content or uploaded file (when known)."
        )

        file_size_bytes: int | None = Field(default=None, description="File size in bytes.")
        checksum_sha256: str | None = Field(default=None, description="SHA-256 checksum.")

        # Lightweight signal only (derived, non-authoritative, and never computed at read time).
        has_structured_data: bool = Field(
            default=False,
            description="True when derived structured data is available for this note.",
        )

        created_at: datetime = Field(description="Record creation timestamp (UTC).")
        updated_at: datetime = Field(description="Record last update timestamp (UTC).")
        deleted_at: datetime | None = Field(
            default=None, description="Soft-delete timestamp (UTC), if deleted."
        )

    items: list[PatientNoteListItemOut] = Field(description="Page of note list items.")
    limit: int = Field(description="Page size requested.", examples=[50])
    next_cursor: str | None = Field(
        default=None,
        description="Opaque cursor for the next page. Omitted/null when there are no more results.",
    )
