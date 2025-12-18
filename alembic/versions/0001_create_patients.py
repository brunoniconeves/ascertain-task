"""create patients table

Revision ID: 0001_create_patients
Revises:
Create Date: 2025-12-17

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_create_patients"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(op.f("ix_patients_name"), "patients", ["name"], unique=False)
    op.create_index(op.f("ix_patients_date_of_birth"), "patients", ["date_of_birth"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_patients_date_of_birth"), table_name="patients")
    op.drop_index(op.f("ix_patients_name"), table_name="patients")
    op.drop_table("patients")
