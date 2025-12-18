from __future__ import annotations

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
from app.patients.service import get_patient
from app.patients.notes.schemas import PatientNoteCreateJson, PatientNoteListOut, PatientNoteOut
from app.patients.notes.service import (
    create_file_patient_note,
    create_inline_patient_note,
    get_patient_note,
    list_patient_notes,
    soft_delete_patient_note,
)
from app.patients.notes.storage import LocalFileStorage, PayloadTooLargeError, StorageIOError

router = APIRouter(prefix="/{patient_id}/notes", tags=["patient-notes"])

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


@router.get("", response_model=PatientNoteListOut)
async def list_notes(
    patient_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
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
        items=[PatientNoteOut.model_validate(n) for n in items],
        limit=limit,
        next_cursor=next_cursor,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PatientNoteOut)
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
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="taken_at is required")

        try:
            taken_at = TypeAdapter(datetime).validate_python(taken_at_raw)
        except ValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc

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


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
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

    # Soft delete for auditability, but ensure file is removed so DB "deleted" implies content is gone.
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


