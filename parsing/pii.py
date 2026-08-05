"""Three-layer PII stripping (SPECIFICATION.md Section 9.4), applied
before any scoring input is built:

1. Regex layer: emails, phone numbers, URLs/social handles, street
   addresses, and other structured PII patterns (DOB, age, gender,
   pronouns, marital status, nationality) are removed from scoring
   text.
2. Header layer: all text above the first detected section heading is
   classified as the contact block and excluded from scoring inputs
   entirely (handled by resume_parser.py, which is the only caller
   that knows where the sections start - this module only strips
   patterns from text it's handed).
3. NER backstop: spaCy PERSON entities anywhere in the remaining text
   are masked, catching a name that appears somewhere other than the
   contact block (e.g. "Reported directly to Jane Smith").

`raw_resume_text` is stored for audit but is never an input to
matching/scoring (Section 9.4) - callers must only extract structured
data from the cleaned text this module returns, never from the raw
original.
"""

from __future__ import annotations

import re
from functools import lru_cache

_REDACTED = "[REDACTED]"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
SOCIAL_HANDLE_RE = re.compile(
    r"\b(?:linkedin\.com|github\.com|twitter\.com|x\.com|instagram\.com)/\S+",
    re.IGNORECASE,
)
# International-tolerant: optional country code, then 2-3 grouped chunks of
# digits separated by spaces/dots/dashes/parens - matches "(555) 010-1001",
# "+1-555-010-1001", "555.010.1001", etc., while requiring enough digits
# that it won't fire on short unrelated numbers.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]\d{3,4}[-.\s]\d{3,4}(?!\d)"
)
STREET_ADDRESS_RE = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.\s]+?\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Circle|Cir)\.?\b",
    re.IGNORECASE,
)
DOB_RE = re.compile(
    r"\b(?:DOB|Date of Birth)\s*:?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.IGNORECASE
)
AGE_RE = re.compile(r"\bAge\s*:?\s*\d{1,3}\b", re.IGNORECASE)
GENDER_RE = re.compile(
    r"\b(?:Gender|Sex)\s*:?\s*(?:Male|Female|Non-binary|Other)\b", re.IGNORECASE
)
PRONOUN_RE = re.compile(
    r"\b(?:He/Him|She/Her|They/Them|Pronouns?\s*:?\s*\w+/\w+)\b", re.IGNORECASE
)
MARITAL_RE = re.compile(
    r"\bMarital Status\s*:?\s*(?:Single|Married|Divorced|Widowed)\b", re.IGNORECASE
)
NATIONALITY_RE = re.compile(
    r"\b(?:Nationality|Citizenship)\s*:?\s*[A-Za-z]+\b", re.IGNORECASE
)

_REGEX_LAYER = (
    EMAIL_RE,
    URL_RE,
    SOCIAL_HANDLE_RE,
    PHONE_RE,
    STREET_ADDRESS_RE,
    DOB_RE,
    AGE_RE,
    GENDER_RE,
    PRONOUN_RE,
    MARITAL_RE,
    NATIONALITY_RE,
)


def strip_pii_regex(text: str) -> str:
    """Layer 1 (Section 9.4): removes every structured PII pattern this
    module recognizes. Order matters only where patterns could
    overlap (e.g. a phone number embedded in a longer digit run) -
    none of these do."""
    for pattern in _REGEX_LAYER:
        text = pattern.sub(_REDACTED, text)
    return text


@lru_cache(maxsize=1)
def _spacy_nlp_with_ner():
    """Loaded lazily and cached - this is a separate, heavier pipeline
    than parsing.common's NER-excluded one, since PII masking is the
    one place this project actually needs spaCy's NER."""
    import spacy

    return spacy.load("en_core_web_sm", exclude=["lemmatizer"])


def mask_person_entities(
    text: str, protected_terms: frozenset[str] | None = None
) -> str:
    """Layer 3 (Section 9.4): masks every spaCy PERSON entity. Applied
    to the whole (already regex-cleaned) block for better NER context
    than per-line masking would give.

    `protected_terms` (lowercased) are never masked even if spaCy tags
    them PERSON - found via real-data testing: en_core_web_sm's small
    NER model sometimes misreads a proper-noun-shaped technology name
    ("Python") as a person's name, which would otherwise silently
    delete that skill mention from scoring. Callers pass in their
    taxonomy vocabulary (e.g. every skill canonical name/alias) as the
    protected set."""
    if not text.strip():
        return text
    doc = _spacy_nlp_with_ner()(text)
    protected = protected_terms or frozenset()
    person_spans = [
        (ent.start_char, ent.end_char)
        for ent in doc.ents
        if ent.label_ == "PERSON" and ent.text.strip().lower() not in protected
    ]
    if not person_spans:
        return text
    masked = text
    for start, end in sorted(person_spans, reverse=True):
        masked = masked[:start] + _REDACTED + masked[end:]
    return masked


def strip_pii_from_lines(
    lines: list[str], protected_terms: frozenset[str] | None = None
) -> list[str]:
    """Regex layer per line (structured patterns are line-local and
    line-order-preserving), then NER masking on the joined block for
    context, split back into the original line count. Convenience
    wrapper for callers working with section_detector's line-based
    section lists."""
    if not lines:
        return []
    cleaned = [strip_pii_regex(line) for line in lines]
    masked = mask_person_entities("\n".join(cleaned), protected_terms)
    return masked.split("\n")
