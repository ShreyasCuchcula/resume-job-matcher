"""Required/preferred classification, requirement-item extraction,
importance assignment, and extraction-confidence scoring
(SPECIFICATION.md Section 10.3, 10.4, 10.5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from domain.schemas import JobRequirement
from parsing.certification_extractor import (
    CertificationIndexEntry,
    extract_certification_names,
)
from parsing.education_extractor import (
    DegreeIndexEntry,
    FieldIndexEntry,
    extract_education,
)
from parsing.skill_extractor import SkillIndexEntry, extract_skill_names

# Section 10.3 cue phrases (case-insensitive).
REQUIRED_CUES: tuple[str, ...] = (
    "required",
    "must have",
    "must possess",
    "mandatory",
    "minimum qualification",
    "essential",
    "candidates must",
    "minimum of",
)
PREFERRED_CUES: tuple[str, ...] = (
    "preferred",
    "desired",
    "ideally",
    "a plus",
    "nice to have",
    "bonus",
    "familiarity with",
    "exposure to",
)

# Importance tiers (Section 10.4): which cues count as "explicit
# must/mandatory wording" (importance 3) versus "standard" preferred
# wording (importance 2, "preferred"/"desired") versus weak/hedging
# wording (importance 1). Cues not listed here but present in
# REQUIRED_CUES/PREFERRED_CUES ("minimum qualification", "minimum of")
# are treated as moderate/standard membership, not explicit strength.
_STRONG_REQUIRED_CUES = frozenset(
    {
        "must have",
        "must possess",
        "mandatory",
        "required",
        "essential",
        "candidates must",
    }
)
_STRONG_PREFERRED_CUES = frozenset({"preferred", "desired"})

_CONFIDENCE_BASE = 0.30
_CONFIDENCE_TAXONOMY_MATCH = 0.25
_CONFIDENCE_CUE = 0.20
_CONFIDENCE_HEADING = 0.15
_CONFIDENCE_EXACT_PATTERN = 0.10


def _cue_pattern(cue: str) -> re.Pattern:
    return re.compile(r"\b" + re.escape(cue) + r"\b", re.IGNORECASE)


_REQUIRED_CUE_PATTERNS = {cue: _cue_pattern(cue) for cue in REQUIRED_CUES}
_PREFERRED_CUE_PATTERNS = {cue: _cue_pattern(cue) for cue in PREFERRED_CUES}


def find_matching_cues(sentence: str, cue_patterns: dict[str, re.Pattern]) -> list[str]:
    return [cue for cue, pattern in cue_patterns.items() if pattern.search(sentence)]


@dataclass(frozen=True)
class SentenceClassification:
    text: str
    section: (
        str | None
    )  # "required" | "preferred" | "responsibilities" | "excluded" | None
    required: bool | None  # None = ambiguous (Section 10.3 priority rule 3)
    matched_cues: tuple[str, ...]
    from_heading_section: bool


def classify_sentence(
    sentence: str, section: str | None, has_headings: bool
) -> SentenceClassification:
    """Section 10.3 priority: (1) explicit sentence wording beats
    (2) section heading beats (3) ambiguous."""
    required_cues = find_matching_cues(sentence, _REQUIRED_CUE_PATTERNS)
    preferred_cues = find_matching_cues(sentence, _PREFERRED_CUE_PATTERNS)

    if required_cues:
        required, matched_cues = True, required_cues
    elif preferred_cues:
        required, matched_cues = False, preferred_cues
    elif section == "required":
        required, matched_cues = True, []
    elif section == "preferred":
        required, matched_cues = False, []
    else:
        required, matched_cues = None, []

    from_heading = has_headings and section in ("required", "preferred")
    return SentenceClassification(
        sentence, section, required, tuple(matched_cues), from_heading
    )


def compute_importance(required: bool, matched_cues: tuple[str, ...]) -> int:
    """Section 10.4: 3 = explicit must/mandatory wording, 2 = standard
    list membership, 1 = weak/hedging wording. Applied uniformly to
    every requirement type (skill/education/certification) per the
    sentence's own wording - the spec states no type-specific carve-out."""
    if required:
        return 3 if any(cue in _STRONG_REQUIRED_CUES for cue in matched_cues) else 2
    if any(cue in _STRONG_PREFERRED_CUES for cue in matched_cues):
        return 2
    if matched_cues:
        return 1
    return 2  # heading-derived preferred item with no per-sentence cue: standard membership


def compute_confidence(
    *, has_cue: bool, from_heading: bool, exact_pattern_bonus: bool
) -> float:
    """Section 10.5: start at 0.30, add bonuses, clamp to [0, 1].
    `taxonomy_matched` isn't a parameter here because every caller of
    this function only calls it once a taxonomy match has already
    been found - the +0.25 always applies."""
    confidence = _CONFIDENCE_BASE + _CONFIDENCE_TAXONOMY_MATCH
    if has_cue:
        confidence += _CONFIDENCE_CUE
    if from_heading:
        confidence += _CONFIDENCE_HEADING
    if exact_pattern_bonus:
        confidence += _CONFIDENCE_EXACT_PATTERN
    return min(1.0, max(0.0, round(confidence, 2)))


@dataclass(frozen=True)
class ExtractorContext:
    skill_index: list[SkillIndexEntry]
    degree_index: list[DegreeIndexEntry]
    field_index: list[FieldIndexEntry]
    certification_index: list[CertificationIndexEntry]


def _education_canonical_name(degree_level: str, field_of_study: str | None) -> str:
    return f"{degree_level} in {field_of_study}" if field_of_study else degree_level


def extract_requirements_from_sentence(
    classification: SentenceClassification, context: ExtractorContext
) -> list[JobRequirement]:
    """Extracts zero or more JobRequirement items (skills, education,
    certifications) from one already-classified sentence."""
    # Ambiguous sentences (Section 10.3 case 3) default to required=True
    # for storage (the schema has no third state) but never get the cue
    # or heading confidence bonus, so they land below the 0.60 review
    # threshold far more often than a confidently-classified item would.
    required = classification.required if classification.required is not None else True
    has_cue = classification.required is not None and bool(classification.matched_cues)
    from_heading = classification.from_heading_section
    importance = compute_importance(required, classification.matched_cues)

    items: list[JobRequirement] = []

    for skill_name in extract_skill_names(classification.text, context.skill_index):
        items.append(
            JobRequirement(
                requirement_id=uuid4(),
                type="skill",
                canonical_name=skill_name,
                original_text=classification.text,
                importance=importance,
                confidence=compute_confidence(
                    has_cue=has_cue,
                    from_heading=from_heading,
                    exact_pattern_bonus=False,
                ),
                required=required,
            )
        )

    education = extract_education(
        classification.text, context.degree_index, context.field_index
    )
    if education is not None:
        items.append(
            JobRequirement(
                requirement_id=uuid4(),
                type="education",
                canonical_name=_education_canonical_name(
                    education.degree_level, education.field_of_study
                ),
                original_text=classification.text,
                importance=importance,
                confidence=compute_confidence(
                    has_cue=has_cue, from_heading=from_heading, exact_pattern_bonus=True
                ),
                required=required,
                allows_equivalent_experience=education.allows_equivalent_experience,
                equivalent_years=education.equivalent_years,
                degree_level=education.degree_level,
                field_of_study=education.field_of_study,
            )
        )

    for cert_name in extract_certification_names(
        classification.text, context.certification_index
    ):
        items.append(
            JobRequirement(
                requirement_id=uuid4(),
                type="certification",
                canonical_name=cert_name,
                original_text=classification.text,
                importance=importance,
                confidence=compute_confidence(
                    has_cue=has_cue, from_heading=from_heading, exact_pattern_bonus=True
                ),
                required=required,
            )
        )

    return items


def merge_duplicate_requirements(items: list[JobRequirement]) -> list[JobRequirement]:
    """Section 10.4: "Duplicate canonical items merge, keeping highest
    importance." Applied across the whole document (required and
    preferred together): if the same (type, canonical_name) is
    mentioned more than once - including the rare contradictory case
    of being called both required and preferred in different
    sentences - only the strongest mention survives. Required beats
    preferred on a tie (the more specific claim), then higher
    importance, then higher confidence, then first-seen order.
    """
    best: dict[tuple[str, str], JobRequirement] = {}
    order: list[tuple[str, str]] = []

    for item in items:
        key = (item.type, item.canonical_name)
        if key not in best:
            order.append(key)
            best[key] = item
            continue
        current = best[key]
        challenger_rank = (item.required, item.importance, item.confidence)
        current_rank = (current.required, current.importance, current.confidence)
        if challenger_rank > current_rank:
            best[key] = item

    return [best[key] for key in order]
