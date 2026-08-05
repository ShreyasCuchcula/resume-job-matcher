"""PDF text extraction (SPECIFICATION.md Section 8.2). Uses PyMuPDF's
text layer only - this project never OCRs a scanned page (Section
1.4); a PDF with no text layer simply extracts short/empty and gets
caught by the probable-scan check in ingestion/validation.py.
"""

from __future__ import annotations

import fitz

from domain.exceptions import CorruptFileError


def pdf_needs_password(file_bytes: bytes) -> bool:
    """Cheap check for the Upload page to explain *why* a file was
    rejected, without going through the exception path in
    extract_pdf_text(). Any failure to even open the file is reported
    as "not password-protected" here - extract_pdf_text() is the
    authority on whether the file is readable at all."""
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            return bool(doc.needs_pass)
    except Exception:
        return False


def extract_pdf_text(file_bytes: bytes) -> str:
    """Exact contract from Section 8.2: raises CorruptFileError for a
    password-protected PDF or any library-level failure to read it.
    Never raises anything else - callers only need to catch one
    exception type to implement the Section 8.1 step 5 "corrupt" path.
    """
    try:
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            if doc.needs_pass:
                raise CorruptFileError("password-protected")
            return "\n".join(page.get_text("text") for page in doc)
    except CorruptFileError:
        raise
    except Exception as exc:
        raise CorruptFileError(f"Unable to extract PDF text: {exc}") from exc
