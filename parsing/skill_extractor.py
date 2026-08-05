"""Taxonomy-driven skill extraction: longest-match-first dictionary
matching over normalized text using the alias map (SPECIFICATION.md
Section 9.3, Section 10.4): "machine learning" matches before
"learning"; "power bi" matches before "bi".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Aliases/canonical names this short (<=2 chars) and purely alphabetic
# ("r", "go", "ml", "js", "ts", "cv", "dl") are ordinary English words
# or common abbreviations in unrelated contexts. Requiring the matched
# span to be capitalized in the original text ("R", "Go", "ML", ...) -
# how these are conventionally written as skills - avoids constantly
# firing on lowercase prose. This doesn't fully eliminate false
# positives (a sentence-initial "Go" would still match) but removes
# the overwhelming majority of them; a known, documented limitation.
_SHORT_AMBIGUOUS_MAX_LEN = 2

_WORD_BOUNDARY = r"(?<![a-zA-Z0-9])"
_WORD_BOUNDARY_END = r"(?![a-zA-Z0-9])"


@dataclass(frozen=True)
class SkillMatch:
    canonical_name: str
    matched_text: str
    start: int
    end: int


@dataclass(frozen=True)
class SkillIndexEntry:
    phrase: str  # lowercase
    canonical_name: str
    case_sensitive: bool
    pattern: re.Pattern


def build_skill_index(skills_taxonomy: dict[str, Any]) -> list[SkillIndexEntry]:
    """One entry per unique canonical/alias phrase, sorted longest-
    phrase-first (by word count, then character count)."""
    entries: list[SkillIndexEntry] = []
    seen_phrases: set[str] = set()

    for canonical, meta in skills_taxonomy.items():
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
                SkillIndexEntry(phrase_lower, canonical, case_sensitive, pattern)
            )

    entries.sort(key=lambda e: (-len(e.phrase.split()), -len(e.phrase)))
    return entries


def find_skills(text: str, skill_index: list[SkillIndexEntry]) -> list[SkillMatch]:
    """Longest-match-first, non-overlapping skill matches within `text`.
    A phrase already claimed by an earlier (longer) match never
    matches again in the same span, so "power bi" consumes that span
    before a hypothetical shorter overlapping alias could."""
    consumed = [False] * len(text)
    matches: list[SkillMatch] = []

    for entry in skill_index:
        for m in entry.pattern.finditer(text):
            start, end = m.span()
            if any(consumed[start:end]):
                continue
            matched_text = text[start:end]
            if entry.case_sensitive and not matched_text[:1].isupper():
                continue
            for i in range(start, end):
                consumed[i] = True
            matches.append(SkillMatch(entry.canonical_name, matched_text, start, end))

    matches.sort(key=lambda m: m.start)
    return matches


def extract_skill_names(text: str, skill_index: list[SkillIndexEntry]) -> list[str]:
    """Deduplicated canonical skill names found in `text`, in the order
    they first appear."""
    seen: list[str] = []
    for match in find_skills(text, skill_index):
        if match.canonical_name not in seen:
            seen.append(match.canonical_name)
    return seen
