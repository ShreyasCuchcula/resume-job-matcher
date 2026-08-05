"""Batch resume ingestion orchestration (SPECIFICATION.md Section 8.1,
Section 14.2 step 1, Section 14.3, Section 6.2).

This is the only layer allowed to call both `ingestion` and `db`
(Section 2.2's dependency rule: `ui -> services -> (parsing | matching
| ingestion) -> normalization -> domain`; `db` is called only by
`services`). It runs every uploaded file through the full Section 8.1
validation/extraction sequence, then persists every accepted
candidate + resume in a single transaction so the batch either lands
completely or not at all.

Note on scope: this module stops at "ingested" - raw text extracted,
hashed, deduplicated, and stored. It does not parse that text into a
CandidateProfile (skills, education, evidence bullets); that's
resume_parser.py's job in a later stage. Accordingly, Resume.parsed_json
and Resume.parser_version are left NULL here and filled in by an
UPDATE once parsing exists (see db/models.py and migration 0002).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from config.settings import get_app_config
from db.models import Candidate, Resume
from domain.enums import FileStatus
from domain.exceptions import CorruptFileError
from ingestion.docx_reader import extract_docx_text
from ingestion.hashing import is_duplicate, sha256_hex, stored_filename
from ingestion.pdf_reader import extract_pdf_text
from ingestion.validation import (
    extension_of,
    is_probable_scan,
    validate_before_extraction,
)

logger = logging.getLogger(__name__)

_EXTRACTORS = {"pdf": extract_pdf_text, "docx": extract_docx_text}
_MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    content: bytes


@dataclass
class IngestionResult:
    """One row of the per-file status table described in Section 15.2."""

    original_filename: str
    status: FileStatus
    code: str
    message: str
    sha256: str | None = None
    size_bytes: int = 0
    candidate_id: UUID | None = None
    display_identifier: str | None = None


@dataclass
class _Accepted:
    """Everything needed to persist one candidate, held in memory until
    the whole batch has been validated and is ready to commit
    together."""

    result: IngestionResult
    file_bytes: bytes
    extension: str
    raw_text: str


def existing_resume_hashes(session: Session) -> set[str]:
    """Every file_hash already persisted from a prior batch - the DB
    side of duplicate detection (Section 8.1 step 4). The only
    ingestion-adjacent read that touches the DB directly, which is
    why it lives here rather than in `ingestion`."""
    return {row[0] for row in session.query(Resume.file_hash).all()}


def ingest_resume_batch(
    session: Session,
    files: list[UploadedFile],
    *,
    upload_dir: Path | None = None,
) -> list[IngestionResult]:
    """Runs Section 8.1's full per-file validation sequence over an
    upload batch, persists every accepted candidate + resume in one
    transaction (Section 6.2: the whole batch commits together or not
    at all), and returns a status for every file, in the order given.
    An unexpected failure on one file never stops the rest.
    """
    config = get_app_config()
    upload_dir = (
        Path(upload_dir) if upload_dir is not None else Path(config.settings.upload_dir)
    )
    upload_dir.mkdir(parents=True, exist_ok=True)
    max_mb = config.scoring.uploads.maximum_resume_mb
    min_chars = config.scoring.uploads.min_extracted_chars

    known_hashes = existing_resume_hashes(session)
    results: list[IngestionResult] = []
    accepted: list[_Accepted] = []

    for uploaded in files:
        try:
            result, accepted_entry = _process_one_file(
                uploaded, known_hashes=known_hashes, max_mb=max_mb, min_chars=min_chars
            )
        except Exception as exc:  # one bad file must never abort the batch
            logger.exception("Unexpected ingestion failure for %s", uploaded.filename)
            result, accepted_entry = (
                IngestionResult(
                    original_filename=uploaded.filename,
                    status="failed",
                    code="UNEXPECTED_ERROR",
                    message=f"Unexpected error while processing this file: {exc}",
                    size_bytes=len(uploaded.content),
                ),
                None,
            )

        results.append(result)
        if accepted_entry is not None:
            accepted.append(accepted_entry)
            known_hashes.add(
                result.sha256
            )  # catches later duplicates within this same batch

    if accepted:
        _persist_batch(session, accepted, upload_dir)

    return results


def _process_one_file(
    uploaded: UploadedFile, *, known_hashes: set[str], max_mb: int, min_chars: int
) -> tuple[IngestionResult, _Accepted | None]:
    filename = uploaded.filename
    file_bytes = uploaded.content
    size_bytes = len(file_bytes)

    failure = validate_before_extraction(filename, file_bytes, maximum_mb=max_mb)
    if failure is not None:
        return (
            IngestionResult(
                original_filename=filename,
                status=failure.status,
                code=failure.code,
                message=failure.message,
                size_bytes=size_bytes,
            ),
            None,
        )

    digest = sha256_hex(file_bytes)
    if is_duplicate(digest, known_hashes):
        return (
            IngestionResult(
                original_filename=filename,
                status="duplicate",
                code="DUPLICATE_FILE",
                message="An identical file has already been uploaded.",
                sha256=digest,
                size_bytes=size_bytes,
            ),
            None,
        )

    extension = extension_of(filename)
    try:
        text = _EXTRACTORS[extension](file_bytes)
    except CorruptFileError as exc:
        is_password = str(exc) == "password-protected"
        return (
            IngestionResult(
                original_filename=filename,
                status="corrupt",
                code="PASSWORD_PROTECTED" if is_password else "CORRUPT_FILE",
                message=(
                    "This PDF is password-protected and cannot be read."
                    if is_password
                    else f"This file could not be read: {exc}"
                ),
                sha256=digest,
                size_bytes=size_bytes,
            ),
            None,
        )

    if is_probable_scan(text, min_chars):
        return (
            IngestionResult(
                original_filename=filename,
                status="probable_scan",
                code="PROBABLE_SCAN",
                message=(
                    f"Only {len(text.strip())} characters of text were found "
                    f"(minimum {min_chars}). This looks like a scanned/image "
                    f"document - OCR is not supported in the MVP."
                ),
                sha256=digest,
                size_bytes=size_bytes,
            ),
            None,
        )

    result = IngestionResult(
        original_filename=filename,
        status="accepted",
        code="OK",
        message="File accepted.",
        sha256=digest,
        size_bytes=size_bytes,
    )
    accepted_entry = _Accepted(
        result=result, file_bytes=file_bytes, extension=extension, raw_text=text
    )
    return result, accepted_entry


def _persist_batch(
    session: Session, accepted: list[_Accepted], upload_dir: Path
) -> None:
    """Writes every accepted file to uploads/{sha256}.{ext} and inserts
    its Candidate + Resume rows in one DB transaction. Section 14.3:
    display identifiers are assigned by ascending SHA-256 across this
    batch, so an identical file set always yields identical numbering.

    On any DB failure the whole transaction rolls back, every file
    written to disk during this call is removed again, and every
    entry's result is downgraded to status="failed" - callers still
    get a full, accurate per-file report rather than an exception that
    silently drops the rest of the batch's statuses (duplicate/
    unsupported/corrupt/probable_scan entries, computed before this
    point, are unaffected either way).
    """
    ordered = sorted(accepted, key=lambda entry: entry.result.sha256)
    written_paths: list[Path] = []
    candidates: list[Candidate] = []

    try:
        for index, entry in enumerate(ordered, start=1):
            display_identifier = f"Candidate {index:03d}"
            digest = entry.result.sha256
            path = upload_dir / stored_filename(digest, entry.extension)
            path.write_bytes(entry.file_bytes)
            written_paths.append(path)

            candidate = Candidate(display_identifier=display_identifier)
            resume = Resume(
                candidate=candidate,
                original_filename=entry.result.original_filename,
                file_path=str(path),
                file_hash=digest,
                mime_type=_MIME_TYPES[entry.extension],
                raw_text=entry.raw_text,
                parsed_json=None,
                parser_version=None,
            )
            session.add(candidate)
            session.add(resume)
            candidates.append(candidate)
            entry.result.display_identifier = display_identifier

        session.commit()

        # Attribute access below triggers SQLAlchemy's post-commit reload
        # of each expired instance's primary key - no extra queries needed
        # beyond that per-object refresh.
        for entry, candidate in zip(ordered, candidates):
            entry.result.candidate_id = candidate.id

    except Exception:
        session.rollback()
        for path in written_paths:
            path.unlink(missing_ok=True)
        for entry in accepted:
            entry.result.status = "failed"
            entry.result.code = "DB_WRITE_FAILED"
            entry.result.message = (
                "Could not save this candidate due to a database error; please retry."
            )
            entry.result.candidate_id = None
            entry.result.display_identifier = None
        logger.exception(
            "Batch persistence failed; rolled back %d candidate(s).", len(accepted)
        )
