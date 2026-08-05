"""Content hashing and duplicate detection (SPECIFICATION.md Section
8.1 step 4, Section 3.3, Section 14.3). Pure functions only - the
actual "is this hash already in the DB" query lives in the services
layer, which is the only layer allowed to talk to `db` (Section 2.2).
"""

from __future__ import annotations

import hashlib


def sha256_hex(file_bytes: bytes) -> str:
    """Content hash of the raw, as-uploaded bytes. This is the basis
    for duplicate detection, the server-generated storage filename,
    and the deterministic candidate ordering in Section 14.3."""
    return hashlib.sha256(file_bytes).hexdigest()


def stored_filename(sha256_hex_digest: str, extension: str) -> str:
    """Server-generated `{sha256}.{ext}` name (Section 8.1 step 7,
    Section 17.2). Never derived from the original filename, so there
    is nothing to sanitize or path-traverse with."""
    return f"{sha256_hex_digest}.{extension.lower().lstrip('.')}"


def is_duplicate(sha256_hex_digest: str, known_hashes: set[str]) -> bool:
    """True if this content hash has already been seen - either
    earlier in the current upload batch or in a prior scoring run's
    persisted resumes. Either way, Section 8.1 step 4 requires no new
    candidate be created for it."""
    return sha256_hex_digest in known_hashes
