from __future__ import annotations

from io import BytesIO
import os
import zipfile
from http import HTTPStatus
from fastapi import UploadFile

from libs import raise_http

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt"}
MIME_BY_EXTENSION = {
    "pdf": {"application/pdf"},
    "doc": {"application/msword", "application/octet-stream"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    "txt": {"text/plain", "application/octet-stream"},
}
def _extract_extension(filename: str | None) -> str:
    if not filename:
        raise_http(HTTPStatus.BAD_REQUEST, "filename_missing", "Filename is required")

    safe_filename = filename
    extension = os.path.splitext(safe_filename)[1].lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise_http(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "unsupported_file_format",
            "Unsupported resume file format",
            {"allowed_formats": sorted(ALLOWED_EXTENSIONS)},
        )
    return extension


def _validate_mime_type(content_type: str | None, extension: str) -> None:
    if not content_type:
        return

    allowed_mimes = MIME_BY_EXTENSION.get(extension, set())
    if content_type not in allowed_mimes:
        raise_http(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "invalid_content_type",
            "Invalid content type for selected file extension",
            {"extension": extension, "content_type": content_type},
        )


def _validate_file_bytes(content: bytes, extension: str) -> None:
    if not content:
        raise_http(HTTPStatus.BAD_REQUEST, "empty_file", "Uploaded file is empty")

    if extension == "pdf":
        if not content.startswith(b"%PDF-"):
            raise_http(HTTPStatus.UNPROCESSABLE_CONTENT, "invalid_pdf", "Uploaded file is not a valid PDF")
        if b"%%EOF" not in content[-4096:]:
            raise_http(HTTPStatus.UNPROCESSABLE_CONTENT, "corrupted_pdf", "PDF file appears to be corrupted")

    if extension == "doc":
        if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise_http(HTTPStatus.UNPROCESSABLE_CONTENT, "invalid_doc", "Uploaded file is not a valid DOC")

    if extension == "docx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                bad_file = archive.testzip()
                if bad_file:
                    raise_http(
                        HTTPStatus.UNPROCESSABLE_CONTENT,
                        "corrupted_docx",
                        "DOCX archive is corrupted",
                        {"broken_entry": bad_file},
                    )
                if "word/document.xml" not in archive.namelist():
                    raise_http(HTTPStatus.UNPROCESSABLE_CONTENT, "invalid_docx", "Uploaded file is not a valid DOCX")
        except zipfile.BadZipFile:
            raise_http(HTTPStatus.UNPROCESSABLE_CONTENT, "invalid_docx", "Uploaded file is not a valid DOCX")

    if extension == "txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("cp1251")
            except UnicodeDecodeError:
                raise_http(
                    HTTPStatus.UNPROCESSABLE_CONTENT,
                    "corrupted_txt",
                    "TXT file encoding is not supported",
                    {"supported_encodings": ["utf-8", "cp1251"]},
                )


async def read_and_validate_resume(
    file: UploadFile,
    max_size_bytes: int,
) -> tuple[bytes, int, str, str, str]:
    extension = _extract_extension(file.filename)
    _validate_mime_type(file.content_type, extension)

    size = 0
    chunks: list[bytes] = []

    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > max_size_bytes:
            raise_http(
                HTTPStatus.CONTENT_TOO_LARGE,
                "file_too_large",
                "Resume file exceeds maximum allowed size",
                {"max_size_bytes": max_size_bytes},
            )
        chunks.append(chunk)

    content = b"".join(chunks)
    _validate_file_bytes(content, extension)

    filename = file.filename or f"resume.{extension}"
    content_type = file.content_type or "application/octet-stream"
    return content, size, extension, filename, content_type
