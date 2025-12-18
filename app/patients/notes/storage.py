from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool


class StorageIOError(Exception):
    """Raised for unexpected storage I/O failures (should map to HTTP 500)."""


class PayloadTooLargeError(Exception):
    """Raised when an uploaded note file exceeds the configured maximum size."""


@dataclass(frozen=True)
class StoredFile:
    # Opaque storage key (for local storage: a relative path under base dir).
    key: str
    size_bytes: int
    sha256_hex: str


class NoteStorage:
    """Storage abstraction for note files (local now; S3 later)."""

    async def save(  # noqa: D401
        self,
        *,
        patient_id: uuid.UUID,
        note_id: uuid.UUID,
        upload: UploadFile,
        max_bytes: int,
    ) -> StoredFile:
        raise NotImplementedError

    async def delete(self, *, key: str) -> None:
        raise NotImplementedError


def _safe_join(base_dir: Path, key: str) -> Path:
    """
    Prevent path traversal. `key` must stay within `base_dir`.
    """

    base_dir = base_dir.resolve()
    candidate = (base_dir / key).resolve()
    if base_dir == candidate or base_dir in candidate.parents:
        return candidate
    raise StorageIOError("Invalid storage key")


def _write_upload_to_path(
    *,
    upload: UploadFile,
    dest_path: Path,
    max_bytes: int,
) -> tuple[int, str]:
    """
    Synchronous write (called in a threadpool).
    Returns (size_bytes, sha256_hex).
    """

    hasher = hashlib.sha256()
    size = 0

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Create new file only; avoid overwriting existing files.
    fd = os.open(str(dest_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = upload.file.read(1024 * 1024)  # 1 MiB
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise PayloadTooLargeError("uploaded file exceeds maximum allowed size")
                hasher.update(chunk)
                f.write(chunk)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        # Best-effort cleanup; ignore cleanup errors.
        try:
            dest_path.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
        raise

    return size, hasher.hexdigest()


class LocalFileStorage(NoteStorage):
    """
    Stores files on local disk under a configurable base directory.

    Key format is PHI-safe and UUID-based:
      {patient_id}/{note_id}/{random_uuid}
    """

    def __init__(self, *, base_dir: Path):
        self._base_dir = base_dir

    async def save(
        self,
        *,
        patient_id: uuid.UUID,
        note_id: uuid.UUID,
        upload: UploadFile,
        max_bytes: int,
    ) -> StoredFile:
        random_leaf = uuid.uuid4()
        key = str(Path(str(patient_id)) / str(note_id) / str(random_leaf))
        dest_path = _safe_join(self._base_dir, key)

        try:
            size_bytes, sha256_hex = await run_in_threadpool(
                _write_upload_to_path, upload=upload, dest_path=dest_path, max_bytes=max_bytes
            )
        except PayloadTooLargeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StorageIOError("Failed to write uploaded file") from exc

        return StoredFile(key=key, size_bytes=size_bytes, sha256_hex=sha256_hex)

    async def delete(self, *, key: str) -> None:
        path = _safe_join(self._base_dir, key)
        try:
            path.unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001
            raise StorageIOError("Failed to delete file") from exc


