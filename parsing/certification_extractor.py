"""Certification/license extraction: longest-match-first dictionary
matching over config/taxonomy/certifications.json (SPECIFICATION.md
Section 9.6, Section 10.4). Shared by job and resume parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from domain.schemas import CertificationRecord, ParsingWarning
from parsing.common import split_into_items

_WORD_BOUNDARY = r"(?<![a-zA-Z0-9])"
_WORD_BOUNDARY_END = r"(?![a-zA-Z0-9])"

# Section 9.6 held-vs-pending wording. "candidate"/"pursuing"/
# "preparing for" get the PENDING_CREDENTIAL warning; "coursework"/
# "training" are also not-held but the spec's own table doesn't attach
# a warning to that row, so none is raised for it.
_PENDING_CANDIDATE_RE = re.compile(
    r"\b(candidate|pursuing|preparing for)\b", re.IGNORECASE
)
_COURSEWORK_RE = re.compile(r"\b(coursework|training)\b", re.IGNORECASE)

# Short alphabetic abbreviations ("cap", "csm", "pmp", "psm") can
# collide with ordinary English words ("cap" as in "salary cap").
# Requiring the matched span to be capitalized in the original text -
# how certification acronyms are conventionally written - avoids
# matching them inside normal lowercase prose.
_SHORT_AMBIGUOUS_MAX_LEN = 4


@dataclass(frozen=True)
class CertificationMatch:
    canonical_name: str
    matched_text: str
    start: int
    end: int


@dataclass(frozen=True)
class CertificationIndexEntry:
    phrase: str  # lowercase
    canonical_name: str
    case_sensitive: bool
    pattern: re.Pattern


def build_certification_index(
    certifications_taxonomy: dict[str, Any]
) -> list[CertificationIndexEntry]:
    entries: list[CertificationIndexEntry] = []
    seen_phrases: set[str] = set()

    for canonical, meta in certifications_taxonomy.items():
        for phrase in [canonical, *meta.get("aliases", [])]:
            phrase_lower = phrase.lower()
            if phrase_lower in seen_phrases:
                continue
            seen_phrases.add(phrase_lower)
            case_sensitive = (
                phrase_lower.isalpha() and len(phrase_lower) <= _SHORT_AMBIGUOUS_MAX_LEN
            )
            pattern = re.compile(
                _WORD_BOUNDARY + re.escape(phrase_lower) + _WORD_BOUNDARY_END,
                re.IGNORECASE,
            )
            entries.append(
                CertificationIndexEntry(
                    phrase_lower, canonical, case_sensitive, pattern
                )
            )

    entries.sort(key=lambda e: (-len(e.phrase.split()), -len(e.phrase)))
    return entries


def find_certifications(
    text: str, certification_index: list[CertificationIndexEntry]
) -> list[CertificationMatch]:
    """Longest-match-first, non-overlapping certification matches."""
    consumed = [False] * len(text)
    matches: list[CertificationMatch] = []

    for entry in certification_index:
        for m in entry.pattern.finditer(text):
            start, end = m.span()
            if any(consumed[start:end]):
                continue
            matched_text = text[start:end]
            if entry.case_sensitive and not matched_text[:1].isupper():
                continue
            for i in range(start, end):
                consumed[i] = True
            matches.append(
                CertificationMatch(entry.canonical_name, matched_text, start, end)
            )

    matches.sort(key=lambda m: m.start)
    return matches


def extract_certification_names(
    text: str, certification_index: list[CertificationIndexEntry]
) -> list[str]:
    seen: list[str] = []
    for match in find_certifications(text, certification_index):
        if match.canonical_name not in seen:
            seen.append(match.canonical_name)
    return seen


def determine_held_status(text: str) -> tuple[bool, bool, bool]:
    """Section 9.6. Returns (held, pending, should_warn)."""
    if _PENDING_CANDIDATE_RE.search(text):
        return False, True, True
    if _COURSEWORK_RE.search(text):
        return False, False, False
    return True, False, False


def extract_candidate_certifications(
    certification_lines: list[str],
    certification_index: list[CertificationIndexEntry],
) -> tuple[list[CertificationRecord], list[ParsingWarning]]:
    """Section 9.6, resume side: one CertificationRecord per distinct
    credential mentioned, plus a PENDING_CREDENTIAL warning for each
    one that reads as not-yet-held ("PMP candidate", "pursuing AWS
    Certified Developer", ...). Issue years are never captured at all
    (Section 9.6: "Issue years are ignored for scoring") - there's no
    field for one on CertificationRecord."""
    records: list[CertificationRecord] = []
    warnings: list[ParsingWarning] = []
    seen: set[str] = set()

    for item in split_into_items(certification_lines):
        for cert_name in extract_certification_names(item, certification_index):
            if cert_name in seen:
                continue
            seen.add(cert_name)
            held, pending, should_warn = determine_held_status(item)
            records.append(
                CertificationRecord(
                    canonical_name=cert_name,
                    original_text=item,
                    held=held,
                    pending=pending,
                )
            )
            if should_warn:
                warnings.append(
                    ParsingWarning(
                        code="PENDING_CREDENTIAL",
                        message=f'"{cert_name}" appears to be pending, not yet held: "{item}"',
                        source_text=item,
                    )
                )

    return records, warnings
