from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.settings import get_settings
from app.domain.exceptions import BusinessValidationError
from app.patients.notes.schemas import PatientNoteCreateJson, PatientNoteListOut, PatientNoteOut
from app.patients.notes.service import (
    create_file_patient_note,
    create_inline_patient_note,
    get_patient_note,
    list_patient_notes,
    soft_delete_patient_note,
)
from app.patients.notes.storage import LocalFileStorage, PayloadTooLargeError, StorageIOError
from app.patients.service import get_patient

router = APIRouter(prefix="/{patient_id}/notes", tags=["patient-notes"])
logger = logging.getLogger("app.soap")

_CREATE_NOTE_OPENAPI_EXTRA = {
    "requestBody": {
        "required": True,
        "content": {
            # Inline note creation
            "application/json": {
                "schema": PatientNoteCreateJson.model_json_schema(),
                "examples": {
                    "inline_text": {
                        "summary": "Inline note (text/plain)",
                        "value": {
                            "taken_at": "2025-01-01T12:34:56Z",
                            "note_type": "soap",
                            "content_text": "S: ...\nO: ...\nA: ...\nP: ...",
                            "content_mime_type": "text/plain",
                        },
                    }
                },
            },
            # File-backed note creation
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file", "taken_at"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "taken_at": {"type": "string", "format": "date-time"},
                        "note_type": {"type": "string", "nullable": True},
                    },
                },
                "examples": {
                    "upload_file": {
                        "summary": "Upload a note file",
                        "value": {"taken_at": "2025-01-01T12:34:56Z", "note_type": "soap"},
                    }
                },
            },
        },
    }
}


def _sniff_mime_type(upload) -> str | None:
    """
    Best-effort MIME detection without external deps.
    We do NOT log filenames or content.
    """

    # Try sniffing magic bytes (works even if client sends wrong Content-Type).
    f = getattr(upload, "file", None)
    if f is None:
        return None
    try:
        pos = f.tell()
        # Ensure we read from the start; form parsers may leave the cursor at EOF.
        f.seek(0)
        head = f.read(16)
        f.seek(pos)
    except Exception:  # noqa: BLE001
        head = b""

    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"

    # Fallback to extension-based guess (still safe; don't log it).
    filename = getattr(upload, "filename", None)
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        return guessed

    return None


def _determine_allowed_mime_type(*, upload, allowed: set[str]) -> str:
    """
    Determine MIME type for an upload, preferring reliable values,
    while enforcing the allowlist.
    """

    sniffed = (_sniff_mime_type(upload) or "").lower().strip()
    if sniffed in allowed:
        # If we can confidently identify a binary format, prefer sniffing even if the client
        # claimed a different (but still allowed) type like text/plain.
        provided = (getattr(upload, "content_type", None) or "").lower().strip()
        if sniffed in {"application/pdf", "image/png", "image/jpeg"} and provided != sniffed:
            return sniffed

        # Otherwise prefer the provided value (if allowed) to avoid surprising callers.
        if provided in allowed:
            return provided
        return sniffed

    provided = (getattr(upload, "content_type", None) or "").lower().strip()
    if provided in allowed:
        return provided

    # If provided but not allowed, report it; otherwise use sniffed or a generic fallback.
    return provided or sniffed or "application/octet-stream"


@router.get(
    "",
    response_model=PatientNoteListOut,
    summary="List notes",
    description=(
        "Return a cursor-paginated list of notes for a patient.\n\n"
        "List items do not include the full derived structured payload. Use "
        "`GET /patients/{patient_id}/notes/{note_id}` for details."
    ),
    responses={
        400: {"description": "Invalid query parameters (e.g. malformed cursor)."},
        404: {"description": "Patient not found."},
    },
)
async def list_notes(
    patient_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of items to return."),
    cursor: str | None = Query(
        default=None, description="Cursor for pagination (use `next_cursor` from previous response)."
    ),
    session: AsyncSession = Depends(get_session),
) -> PatientNoteListOut:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    try:
        items, next_cursor = await list_patient_notes(
            session=session, patient_id=patient_id, limit=limit, cursor=cursor
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PatientNoteListOut(
        # List items intentionally do not embed the full derived structured payload.
        # Instead they include `has_structured_data`; callers can fetch details via GET /{note_id}.
        items=[PatientNoteListOut.PatientNoteListItemOut.model_validate(n) for n in items],
        limit=limit,
        next_cursor=next_cursor,
    )


@router.get(
    "/{note_id}",
    response_model=PatientNoteOut,
    response_model_exclude_none=False,
    summary="Get note",
    description=(
        "Fetch a single note.\n\n"
        "When `structured_data` is present, it is derived (best-effort) and non-authoritative."
    ),
    responses={
        404: {"description": "Patient or note not found."},
    },
)
async def get_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PatientNoteOut:
    """
    Fetch a single note.

    Response is backwards-compatible and includes optional derived structured data
    (non-authoritative) when it exists; otherwise `structured_data` is null.
    """

    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    note = await get_patient_note(session=session, patient_id=patient_id, note_id=note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    return PatientNoteOut.model_validate(note)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=PatientNoteOut,
    summary="Create note",
    description=(
        "Create a note for a patient.\n\n"
        "Supported request types:\n"
        "- `application/json`: inline text note.\n"
        "- `multipart/form-data`: upload a file note.\n\n"
        "Note content is the source of truth; derived structured data (when available) is stored "
        "separately and marked as non-authoritative."
    ),
    openapi_extra=_CREATE_NOTE_OPENAPI_EXTRA,
    responses={
        400: {"description": "Validation failed (e.g. missing file/taken_at)."},
        404: {"description": "Patient not found."},
        413: {"description": "Uploaded file is too large."},
        415: {"description": "Unsupported media type (must be JSON or multipart/form-data)."},
        422: {"description": "Payload validation failed."},
    },
)
async def create_patient_note(
    patient_id: uuid.UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> PatientNoteOut:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    content_type = (request.headers.get("content-type") or "").lower()
    settings = get_settings()

    # Support either JSON (inline text) or multipart/form-data (file upload).
    if content_type.startswith("application/json"):
        try:
            raw = await request.json()
            payload = PatientNoteCreateJson.model_validate(raw)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
            ) from exc

        try:
            note = await create_inline_patient_note(
                session=session,
                patient=patient,
                taken_at=payload.taken_at,
                note_type=payload.note_type,
                content_text=payload.content_text,
                content_mime_type=payload.content_mime_type,
            )
        except BusinessValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message
            ) from exc

        return PatientNoteOut.model_validate(note)

    if content_type.startswith("multipart/form-data"):
        # NOTE: multipart parsing requires python-multipart.
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="file is required for multipart requests",
            )

        # Starlette returns UploadFile here; type is runtime-checked by usage below.
        taken_at_raw = form.get("taken_at")
        if taken_at_raw is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="taken_at is required"
            )

        try:
            taken_at = TypeAdapter(datetime).validate_python(taken_at_raw)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()
            ) from exc

        note_type_raw = form.get("note_type")
        note_type = str(note_type_raw) if note_type_raw is not None else None

        allowed = set(settings.notes_allowed_mime_types)
        mime_type = _determine_allowed_mime_type(upload=upload, allowed=allowed)
        if mime_type not in allowed:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported media type: {mime_type}",
            )

        note_id = uuid.uuid4()
        if settings.file_storage_backend != "local":
            raise HTTPException(status_code=500, detail="File storage backend is not supported")

        storage = LocalFileStorage(base_dir=Path(settings.local_storage_base_path))
        max_bytes = int(settings.max_note_upload_mb) * 1024 * 1024

        # Best-effort SOAP parsing requires raw text. For file-backed notes we only attempt
        # this for text/plain uploads; parsing is deterministic and must never block creation.
        raw_text_for_parsing: str | None = None
        if (note_type or "").strip().lower() == "soap" and mime_type == "text/plain":
            try:
                f = getattr(upload, "file", None)
                if f is not None:
                    f.seek(0)
                    raw_bytes = f.read()
                    f.seek(0)
                    try:
                        raw_text_for_parsing = raw_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        # Deterministic fallback; do not log content/filenames.
                        raw_text_for_parsing = raw_bytes.decode("utf-8", errors="replace")
                        logger.warning(
                            "SOAP decode used replacement characters (note_id=%s)", str(note_id)
                        )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "SOAP pre-parse read failed; continuing without derived parse (error=%s)",
                    exc.__class__.__name__,
                )

        try:
            stored = await storage.save(
                patient_id=patient.id,
                note_id=note_id,
                upload=upload,
                max_bytes=max_bytes,
            )
        except PayloadTooLargeError as exc:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Uploaded file is too large",
            ) from exc
        except StorageIOError as exc:
            raise HTTPException(status_code=500, detail="File storage failed") from exc

        # Persist DB record after file write; if DB fails, delete the file (best-effort).
        try:
            note = await create_file_patient_note(
                session=session,
                patient=patient,
                note_id=note_id,
                taken_at=taken_at,
                note_type=note_type,
                content_mime_type=mime_type,
                stored_file=stored,
                raw_text_for_parsing=raw_text_for_parsing,
            )
        except Exception:
            try:
                await storage.delete(key=stored.key)
            except Exception:  # noqa: BLE001
                pass
            raise

        return PatientNoteOut.model_validate(note)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Content-Type must be application/json or multipart/form-data",
    )


@router.delete(
    "/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Delete note",
    description=(
        "Soft-delete a note for auditability, and remove any stored file content so a deleted "
        "note implies the content is gone."
    ),
    responses={
        404: {"description": "Patient or note not found."},
        500: {"description": "File deletion/storage backend error."},
    },
)
async def delete_note(
    patient_id: uuid.UUID,
    note_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    patient = await get_patient(session=session, patient_id=patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    note = await get_patient_note(session=session, patient_id=patient_id, note_id=note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    # Soft delete for auditability. Ensure file is removed so DB "deleted" implies content is gone.
    settings = get_settings()
    if note.file_path:
        if settings.file_storage_backend != "local":
            raise HTTPException(status_code=500, detail="File storage backend is not supported")
        storage = LocalFileStorage(base_dir=Path(settings.local_storage_base_path))
        try:
            await storage.delete(key=note.file_path)
        except StorageIOError as exc:
            raise HTTPException(status_code=500, detail="File deletion failed") from exc

    await soft_delete_patient_note(session=session, note=note, deleted_at=datetime.now(UTC))
    return None
