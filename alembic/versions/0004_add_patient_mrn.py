"""add patient mrn

Revision ID: 0004_add_patient_mrn
Revises: 0003_note_structured
Create Date: 2025-12-18

MRN (Medical Record Number) notes:
- MRN is a domain identifier (PHI-adjacent), not a primary key.
- Nullable for backward compatibility with existing rows.
- Unique within the system.
- Immutable once set (enforced with a DB trigger where possible).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_add_patient_mrn"
down_revision = "0003_note_structured"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("patients", sa.Column("mrn", sa.String(length=50), nullable=True))

    # Unique index enforces uniqueness while allowing multiple NULLs (both Postgres + SQLite).
    op.create_index("uq_patients_mrn", "patients", ["mrn"], unique=True)

    bind = op.get_bind()
    dialect = bind.dialect.name

    # Enforce immutability once set at the database level where feasible.
    # This prevents changing/removing a non-null MRN via UPDATE statements.
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS patients_mrn_immutable
            BEFORE UPDATE OF mrn ON patients
            FOR EACH ROW
            WHEN OLD.mrn IS NOT NULL AND (NEW.mrn IS NULL OR NEW.mrn != OLD.mrn)
            BEGIN
              SELECT RAISE(ABORT, 'mrn_immutable');
            END;
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION patients_mrn_immutable_fn()
            RETURNS trigger AS $$
            BEGIN
              IF OLD.mrn IS NOT NULL AND NEW.mrn IS DISTINCT FROM OLD.mrn THEN
                RAISE EXCEPTION 'mrn_immutable';
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER patients_mrn_immutable
            BEFORE UPDATE OF mrn ON patients
            FOR EACH ROW
            EXECUTE FUNCTION patients_mrn_immutable_fn();
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS patients_mrn_immutable;")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS patients_mrn_immutable ON patients;")
        op.execute("DROP FUNCTION IF EXISTS patients_mrn_immutable_fn();")

    op.drop_index("uq_patients_mrn", table_name="patients")
    op.drop_column("patients", "mrn")


