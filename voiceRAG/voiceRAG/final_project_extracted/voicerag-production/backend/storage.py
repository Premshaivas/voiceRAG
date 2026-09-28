from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import UploadFile

from .config import settings

ALLOWED_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga", ".ogg", ".opus", ".wav", ".webm"}
CHUNK_BYTES = 1024 * 1024


async def save_upload(upload: UploadFile, destination: Path) -> int:
    total = 0
    with destination.open("wb") as output:
        while chunk := await upload.read(CHUNK_BYTES):
            total += len(chunk)
            if total > settings.max_upload_mb * 1024 * 1024:
                raise ValueError(f"Uploaded file exceeds {settings.max_upload_mb} MB")
            output.write(chunk)
    return total


def validate_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported media extension: {suffix or 'missing'}")
    return suffix


def remove_file(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass

