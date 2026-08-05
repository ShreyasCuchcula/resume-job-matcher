"""Pure, side-effect-free file validation (SPECIFICATION.md Section 8.1,
steps 1-3 and 6). No I/O, no DB, no filesystem - just bytes in,
verdicts out, so every rule is trivially unit-testable and reusable
from the service layer regardless of where the bytes came from.

Per the dependency rule in Section 2.2 (`ui -> services -> (parsing |
matching | ingestion) -> normalization -> domain`), this module never
imports from `db` or `services`.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from domain.enums import FileStatus

PDF_MAGIC = b"%PDF"
ZIP_MAGIC = b"PK\x03\x04"
DOCX_REQUIRED_ENTRY = "word/document.xml"

DEFAULT_ALLOWED_EXTENSIONS = frozenset({"pdf", "docx"})

_BYTES_PER_MB = 1024 * 1024


@dataclass(frozen=True)
class ValidationFailure:
    """A rejection at the pre-extraction validation stage. Always maps
    to FileStatus == "unsupported" per Section 8.1 steps 1-3 (a bad
    extension, an oversized file, and a signature mismatch are all
    reported to the recruiter the same way: the file was never a
    readable PDF/DOCX in the first place)."""

    status: FileStatus
    code: str
    message: str


def extension_of(filename: str) -> str:
    """Lowercase extension without the leading dot; '' if none."""
    return Path(filename).suffix.lower().lstrip(".")


def has_allowed_extension(
    filename: str, allowed_extensions: frozenset[str] = DEFAULT_ALLOWED_EXTENSIONS
) -> bool:
    return extension_of(filename) in allowed_extensions


def is_within_size_limit(file_bytes: bytes, maximum_mb: int) -> bool:
    return len(file_bytes) <= maximum_mb * _BYTES_PER_MB


def _is_docx_zip(file_bytes: bytes) -> bool:
    """DOCX is a ZIP archive containing word/document.xml (Section 8.1
    step 3). A .docx extension on a non-ZIP file, or a ZIP that lacks
    the Word document part, both fail this check."""
    if not file_bytes.startswith(ZIP_MAGIC):
        return False
    try:
        with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
            return DOCX_REQUIRED_ENTRY in archive.namelist()
    except zipfile.BadZipFile:
        return False


def matches_declared_signature(extension: str, file_bytes: bytes) -> bool:
    """Extension alone is never trusted (Section 8.1 step 3): verify the
    magic bytes actually match what the extension claims."""
    if extension == "pdf":
        return file_bytes.startswith(PDF_MAGIC)
    if extension == "docx":
        return _is_docx_zip(file_bytes)
    return False


def validate_before_extraction(
    filename: str,
    file_bytes: bytes,
    *,
    maximum_mb: int,
    allowed_extensions: frozenset[str] = DEFAULT_ALLOWED_EXTENSIONS,
) -> ValidationFailure | None:
    """Runs Section 8.1 steps 1-3 in order, short-circuiting on the
    first failure. Returns None when the file is clear to proceed to
    text extraction; otherwise returns the ValidationFailure to report."""
    extension = extension_of(filename)

    if extension not in allowed_extensions:
        allowed = ", ".join(f".{ext}" for ext in sorted(allowed_extensions))
        label = f".{extension}" if extension else "(no extension)"
        return ValidationFailure(
            status="unsupported",
            code="UNSUPPORTED_EXTENSION",
            message=f"'{label}' is not a supported file type. Allowed: {allowed}.",
        )

    if not is_within_size_limit(file_bytes, maximum_mb):
        size_mb = len(file_bytes) / _BYTES_PER_MB
        return ValidationFailure(
            status="unsupported",
            code="FILE_TOO_LARGE",
            message=f"File is {size_mb:.1f} MB, which exceeds the {maximum_mb} MB limit.",
        )

    if not matches_declared_signature(extension, file_bytes):
        return ValidationFailure(
            status="unsupported",
            code="SIGNATURE_MISMATCH",
            message=(
                f"File content does not match its .{extension} extension "
                f"(failed magic-byte signature check)."
            ),
        )

    return None


def is_probable_scan(extracted_text: str, min_extracted_chars: int) -> bool:
    """Section 8.1 step 6: extracted text under the threshold means
    there's effectively no text layer - a scanned/image resume, which
    the MVP explicitly does not OCR (Section 1.4)."""
    return len(extracted_text.strip()) < min_extracted_chars
