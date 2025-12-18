"""backfill patient mrn and enforce not null

Revision ID: 0005_patient_mrn_not_null
Revises: 0004_add_patient_mrn
Create Date: 2025-12-18

Rationale:
- We initially introduced MRN as nullable for backward compatibility.
- If we now want MRN to be required everywhere, we must backfill existing rows first,
  then enforce NOT NULL at the DB level.

Backfill strategy:
- MRN is generated deterministically from the patient's UUID bytes:
  MRN-<BASE32(UUID_BYTES)>
- This avoids encoding PHI (not derived from name/DOB).
- Uniqueness is guaranteed because UUID primary keys are unique.
"""

from __future__ import annotations

import base64
import uuid

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_patient_mrn_not_null"
down_revision = "0004_add_patient_mrn"
branch_labels = None
depends_on = None


def _mrn_from_uuid(*, patient_id: uuid.UUID) -> str:
    token = base64.b32encode(patient_id.bytes).decode("ascii").rstrip("=")  # 26 chars
    return f"MRN-{token}"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Backfill any NULL MRNs before enforcing NOT NULL.
    rows = bind.execute(sa.text("SELECT id FROM patients WHERE mrn IS NULL")).fetchall()
    for (raw_id,) in rows:
        # SQLite may return a string; Postgres returns UUID.
        patient_id = raw_id if isinstance(raw_id, uuid.UUID) else uuid.UUID(str(raw_id))
        mrn = _mrn_from_uuid(patient_id=patient_id)
        bind.execute(
            sa.text("UPDATE patients SET mrn = :mrn WHERE id = :id AND mrn IS NULL"),
            {"mrn": mrn, "id": str(patient_id)},
        )

    # Enforce NOT NULL.
    if dialect == "sqlite":
        # SQLite requires batch mode (table rebuild) for altering nullability.
        with op.batch_alter_table("patients") as batch:
            batch.alter_column("mrn", existing_type=sa.String(length=50), nullable=False)

        # Batch mode rebuilds the table; ensure our immutability trigger and unique index still exist.
        # (SQLite doesn't automatically carry over triggers across rebuilds.)
        op.execute("DROP INDEX IF EXISTS uq_patients_mrn;")
        op.create_index("uq_patients_mrn", "patients", ["mrn"], unique=True)
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
    else:
        op.alter_column("patients", "mrn", existing_type=sa.String(length=50), nullable=False)


def downgrade() -> None:
    # Revert NOT NULL, keep values (do not attempt to null-out).
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        with op.batch_alter_table("patients") as batch:
            batch.alter_column("mrn", existing_type=sa.String(length=50), nullable=True)
    else:
        op.alter_column("patients", "mrn", existing_type=sa.String(length=50), nullable=True)


