"""Upload boundary: reject unsafe names, unsupported media, and excessive input sizes."""

import logging
from pathlib import PurePosixPath

from fastapi import UploadFile

from app.errors import InvalidUpload, UploadTooLarge

logger = logging.getLogger(__name__)
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}


def validate_file_type(filename: str | None, content_type: str | None) -> tuple[str, str]:
    """Return a basename and extension only when extension and declared MIME agree."""
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    extension = PurePosixPath(name).suffix.lower()
    if not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise InvalidUpload("Use a filename of 1–255 characters without control characters.")
    if extension not in MIME_TYPES:
        raise InvalidUpload("Only PDF, DOCX, and TXT files are supported.")
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if mime != MIME_TYPES[extension]:
        raise InvalidUpload(f"The MIME type for {extension} must be {MIME_TYPES[extension]}.")
    return name, extension


def read_upload(upload: UploadFile, max_bytes: int) -> tuple[str, str, bytes]:
    """Read at most limit+1 bytes and return validated input for document extraction."""
    try:
        name, extension = validate_file_type(upload.filename, upload.content_type)
        content = upload.file.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise UploadTooLarge("File exceeds MAX_UPLOAD_MB. Upload a smaller document.")
        if not content:
            raise InvalidUpload("The uploaded file is empty.")
        logger.info("Document uploaded: type=%s bytes=%d", extension, len(content))
        return name, extension, content
    finally:
        upload.file.close()
