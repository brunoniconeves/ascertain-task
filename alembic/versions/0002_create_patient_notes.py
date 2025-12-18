"""create patient notes tables

Revision ID: 0002_create_patient_notes
Revises: 0001_create_patients
Create Date: 2025-12-18

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_create_patient_notes"
down_revision = "0001_create_patients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "patient_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("patients.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_type", sa.String(length=50), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(content_text IS NOT NULL) OR (file_path IS NOT NULL)",
            name="patient_notes_has_content",
        ),
        sa.CheckConstraint(
            "NOT (content_text IS NOT NULL AND file_path IS NOT NULL)",
            name="patient_notes_content_xor_file",
        ),
        sa.CheckConstraint(
            "(file_path IS NULL) OR (file_path NOT LIKE '/%' AND file_path NOT LIKE '%..%')",
            name="patient_notes_file_path_relative",
        ),
        sa.CheckConstraint(
            "(checksum_sha256 IS NULL) OR (length(checksum_sha256) = 64)",
            name="patient_notes_checksum_len_64",
        ),
    )

    op.create_index(
        op.f("ix_patient_notes_patient_id"), "patient_notes", ["patient_id"], unique=False
    )
    op.create_index(
        "ix_patient_notes_patient_id_taken_at",
        "patient_notes",
        ["patient_id", "taken_at"],
        unique=False,
    )

    op.create_table(
        "patient_note_text",
        sa.Column(
            "note_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("patient_notes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("patient_note_text")
    op.drop_index("ix_patient_notes_patient_id_taken_at", table_name="patient_notes")
    op.drop_index(op.f("ix_patient_notes_patient_id"), table_name="patient_notes")
    op.drop_table("patient_notes")
