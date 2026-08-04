"""Domain-level exceptions shared across all layers (SPECIFICATION.md
Section 4: `domain/exceptions.py # UnscorableJobError, ParsingError,
ValidationError...`).

These are intentionally plain, information-carrying exceptions with no
side effects (no logging, no I/O) so every layer can raise and catch
them without a dependency on `services` or `ui`.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level exceptions."""


class ValidationError(DomainError):
    """Input failed a domain-level validation rule (Section 10.1, 16).

    Distinct from `pydantic.ValidationError` (schema-shape failures);
    this covers rule-level rejections such as a job description that's
    too short, too long, or has nothing scoreable extracted.
    """


class ParsingError(DomainError):
    """A parser could not produce a usable result from otherwise-valid
    input text (as opposed to `ingestion` failures, which concern the
    raw file itself)."""


class CorruptFileError(DomainError):
    """Raised by the PDF/DOCX extraction functions (Section 8.2) when a
    file cannot be read: password-protected, truncated, or otherwise
    not a valid document of its declared type."""


class UnscorableJobError(DomainError):
    """Raised when a confirmed job profile has no applicable scoring
    components left after weight normalization (Section 13.5) — i.e.
    every one of required/experience/responsibility/preferred is
    inapplicable, so there is nothing to score against."""
