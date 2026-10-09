"""Poster storage in GridFS (``fs.files`` / ``fs.chunks``)."""

from bson import ObjectId
from gridfs.errors import NoFile

from app import db as db_module
from app.core.errors import AppError, not_found

MAX_POSTER_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}


def sniff_image_type(data: bytes) -> str | None:
    """Identify the image from its magic bytes (never trust the client's header or filename)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_poster(data: bytes, declared_type: str | None) -> str:
    if len(data) > MAX_POSTER_BYTES:
        raise AppError(413, "file_too_large", f"Poster must be at most {MAX_POSTER_BYTES // (1024 * 1024)} MB")
    if not data:
        raise AppError(422, "empty_file", "Uploaded file is empty")
    if declared_type not in ALLOWED_TYPES:
        raise AppError(415, "unsupported_media_type", "Poster must be image/png, image/jpeg or image/webp")
    real = sniff_image_type(data)
    if real is None or real != declared_type:
        raise AppError(415, "unsupported_media_type", "File content does not match an allowed image type")
    return real


async def save_poster(data: bytes, content_type: str, event_id: ObjectId) -> ObjectId:
    return await db_module.get_bucket().upload_from_stream(
        f"poster-{event_id}",
        data,
        metadata={"content_type": content_type, "event_id": event_id, "kind": "poster"},
    )


async def delete_file(file_id: ObjectId | None) -> None:
    if file_id is None:
        return
    try:
        await db_module.get_bucket().delete(file_id)
    except NoFile:
        pass


async def open_file(file_id: ObjectId):
    try:
        return await db_module.get_bucket().open_download_stream(file_id)
    except NoFile:
        raise not_found("File") from None
