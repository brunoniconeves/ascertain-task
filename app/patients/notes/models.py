from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class PatientNote(Base):
    """
    Patient note metadata + either inline content OR a reference to a local file.

    Storage rules:
    - Exactly one of `content_text` or `file_path` must be set (see constraints).
    - When a file is present, it is the clinical source of truth; derived/extracted text
      belongs in `PatientNoteText`.
    """

    __tablename__ = "patient_notes"
    __table_args__ = (
        # Must have at least one storage backing (inline text or file reference).
        CheckConstraint(
            "(content_text IS NOT NULL) OR (file_path IS NOT NULL)",
            name="patient_notes_has_content",
        ),
        # Enforce "either-or" for clarity and auditability (no ambiguous precedence).
        CheckConstraint(
            "NOT (content_text IS NOT NULL AND file_path IS NOT NULL)",
            name="patient_notes_content_xor_file",
        ),
        # Basic hardening: local file paths must be relative and not contain traversal.
        # (Application should also enforce this.)
        CheckConstraint(
            "(file_path IS NULL) OR (file_path NOT LIKE '/%' AND file_path NOT LIKE '%..%')",
            name="patient_notes_file_path_relative",
        ),
        # If provided, checksum should look like a 64-char sha256 hex string.
        CheckConstraint(
            "(checksum_sha256 IS NULL) OR (length(checksum_sha256) = 64)",
            name="patient_notes_checksum_len_64",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Inline note content (nullable if file-backed note).
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Local file metadata (nullable if inline note).
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Soft-delete for auditability (retain historical metadata).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    patient = relationship("app.patients.models.Patient", lazy="joined")
    extracted_text = relationship(
        "PatientNoteText",
        uselist=False,
        back_populates="note",
        lazy="selectin",
    )

    @property
    def has_file(self) -> bool:
        return self.file_path is not None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class PatientNoteText(Base):
    """
    Optional derived/extracted text for a file-backed note (e.g. OCR, parsing).

    This is intentionally separate from `patient_notes.content_text` to avoid ambiguity
    and allow independent retention policies later.
    """

    __tablename__ = "patient_note_text"

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("patient_notes.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Extracted/derived plain text (may contain PHI; treat same as note content).
    text: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    note: Mapped[PatientNote] = relationship("PatientNote", back_populates="extracted_text")
