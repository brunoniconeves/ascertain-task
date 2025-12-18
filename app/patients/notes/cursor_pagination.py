from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class NoteCursor:
    patient_id: uuid.UUID
    last_taken_at: datetime
    last_id: uuid.UUID


def encode_note_cursor(*, cursor: NoteCursor) -> str:
    payload = {
        "patient_id": str(cursor.patient_id),
        "last_taken_at": cursor.last_taken_at.isoformat(),
        "last_id": str(cursor.last_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_note_cursor(*, raw: str) -> NoteCursor:
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
        obj = json.loads(decoded.decode("utf-8"))
        return NoteCursor(
            patient_id=uuid.UUID(obj["patient_id"]),
            last_taken_at=datetime.fromisoformat(obj["last_taken_at"]),
            last_id=uuid.UUID(obj["last_id"]),
        )
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid cursor") from exc
