"""Certification/license extraction: longest-match-first dictionary
matching over config/taxonomy/certifications.json (SPECIFICATION.md
Section 9.6, Section 10.4). Shared by job and resume parsing.

Held-vs-pending wording detection (Section 9.6's "PMP candidate" /
"pursuing X" rules) is resume-side logic and belongs to the resume
parser (a later stage); this module only finds *which* credential is
being referred to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_WORD_BOUNDARY = r"(?<![a-zA-Z0-9])"
_WORD_BOUNDARY_END = r"(?![a-zA-Z0-9])"

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
