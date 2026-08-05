"""Taxonomy-driven skill extraction: longest-match-first dictionary
matching over normalized text using the alias map (SPECIFICATION.md
Section 9.3, Section 10.4): "machine learning" matches before
"learning"; "power bi" matches before "bi".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from domain.enums import EvidenceSection
from domain.schemas import CandidateQualification

# Section 9.3 evidence-strength tiers.
EVIDENCE_STRENGTH_BULLET = 1.00  # employment / project / research bullet
EVIDENCE_STRENGTH_SUMMARY = 0.90
EVIDENCE_STRENGTH_SKILLS_SECTION = 0.80

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


def extract_candidate_skills(
    *,
    bullet_texts_by_section: dict[EvidenceSection, list[str]],
    summary_text: str | None,
    skills_section_text: str | None,
    skill_index: list[SkillIndexEntry],
) -> list[CandidateQualification]:
    """Section 9.3: scans every scoreable section and records each
    canonical skill exactly once, keeping its single strongest piece of
    evidence - repetition never adds points. `bullet_texts_by_section`
    should only ever contain "experience"/"project"/"research" bullet
    text (all worth the same 1.00 strength); iterating it in that fixed
    order, then summary, then the skills section, makes tie-breaking
    between equal-strength mentions deterministic (first one found
    wins).

    Extraction confidence is 1.0 for every match here: unlike job-side
    required-vs-preferred classification, a resume skill mention has no
    comparable source of ambiguity - the taxonomy lookup itself is
    exact-or-nothing.
    """
    best: dict[str, CandidateQualification] = {}

    def consider(text: str, section: EvidenceSection, strength: float) -> None:
        if not text:
            return
        for match in find_skills(text, skill_index):
            existing = best.get(match.canonical_name)
            if existing is not None and existing.evidence_strength >= strength:
                continue
            best[match.canonical_name] = CandidateQualification(
                type="skill",
                canonical_name=match.canonical_name,
                original_text=text,
                evidence_section=section,
                evidence_text=text,
                evidence_strength=strength,
                extraction_confidence=1.0,
            )

    for section_name in ("experience", "project", "research"):
        for text in bullet_texts_by_section.get(section_name, []):
            consider(text, section_name, EVIDENCE_STRENGTH_BULLET)

    consider(summary_text or "", "summary", EVIDENCE_STRENGTH_SUMMARY)
    consider(skills_section_text or "", "skills", EVIDENCE_STRENGTH_SKILLS_SECTION)

    return list(best.values())
