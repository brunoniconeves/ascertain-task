"""create patient note structured derived data table

Revision ID: 0003_note_structured
Revises: 0002_create_patient_notes
Create Date: 2025-12-18

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_note_structured"
down_revision = "0002_create_patient_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patient_note_structured",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "note_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("patient_notes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema", sa.String(length=50), nullable=False),
        sa.Column("parsed_from", sa.String(length=50), nullable=False),
        sa.Column("parser_version", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.String(length=20), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "note_id",
            "schema",
            name="patient_note_structured_note_schema_unique",
        ),
    )

    op.create_index(
        op.f("ix_patient_note_structured_note_id"),
        "patient_note_structured",
        ["note_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_patient_note_structured_note_id"), table_name="patient_note_structured")
    op.drop_table("patient_note_structured")


