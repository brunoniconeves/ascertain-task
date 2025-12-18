from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PatientCursor:
    sort: str
    order: str
    name: str | None
    last_id: uuid.UUID
    last_value: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii")


def _b64url_decode(data: str) -> bytes:
    # Accept paddingless cursors too.
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def encode_patient_cursor(
    *, sort: str, order: str, name: str | None, last_id: uuid.UUID, last_value: str
) -> str:
    payload = {
        "v": 1,
        "sort": sort,
        "order": order,
        "name": name,
        "last": {"id": str(last_id), "value": last_value},
    }
    return _b64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def decode_patient_cursor(*, cursor: str, sort: str, order: str, name: str | None) -> PatientCursor:
    try:
        payload = json.loads(_b64url_decode(cursor))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid cursor") from exc

    if payload.get("v") != 1:
        raise ValueError("Invalid cursor version")

    if payload.get("sort") != sort or payload.get("order") != order or payload.get("name") != name:
        raise ValueError("Cursor does not match current query")

    last = payload.get("last") or {}
    last_id = uuid.UUID(last.get("id"))
    last_value = last.get("value")
    if not isinstance(last_value, str) or not last_value:
        raise ValueError("Invalid cursor payload")

    return PatientCursor(sort=sort, order=order, name=name, last_id=last_id, last_value=last_value)


def parse_cursor_value(*, sort: str, raw: str) -> str | date | datetime:
    if sort == "created_at":
        return datetime.fromisoformat(raw)
    if sort == "date_of_birth":
        return date.fromisoformat(raw)
    return raw


def format_cursor_value(*, sort: str, value: str | date | datetime) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)
