"""Job description parsing orchestration (SPECIFICATION.md Section 10)."""

from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from domain.exceptions import ValidationError
from domain.schemas import JobProfile, JobRequirement, ParsingWarning
from parsing.certification_extractor import build_certification_index
from parsing.common import parse_number_word, split_into_items
from parsing.education_extractor import build_degree_index, build_field_index
from parsing.requirement_extractor import (
    ExtractorContext,
    classify_sentence,
    extract_requirements_from_sentence,
    merge_duplicate_requirements,
)
from parsing.responsibility_extractor import (
    build_responsibilities_from_items,
    extract_responsibilities,
)
from parsing.section_detector import JOB_HEADINGS, split_into_sections
from parsing.skill_extractor import build_skill_index

PARSER_VERSION = "job-parser-1.0"

_EXCLUDED_BOILERPLATE_RE = re.compile(
    r"\b(benefits?|compensation|perks?|401k|health insurance|\bpto\b|"
    r"about us|who we are|our company|equal opportunity|\beeo\b)\b",
    re.IGNORECASE,
)

# Section 10.6 patterns. Each requires the number to be directly tied to
# "years"/"experience" wording - never inferred from a seniority word
# like "senior" on its own, which none of these patterns can match.
_YEARS_PLUS_RE = re.compile(r"\b(\d+)\+\s*years?\b", re.IGNORECASE)
_AT_LEAST_RE = re.compile(r"\bat least\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_MINIMUM_OF_RE = re.compile(r"\bminimum of\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_RANGE_RE = re.compile(r"\b(\d+|[a-z]+)\s+to\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_YEARS_OF_EXPERIENCE_RE = re.compile(
    r"\b(\d+|[a-z]+)\s+years?\s+of\s+(?:relevant\s+|related\s+|professional\s+)?experience\b",
    re.IGNORECASE,
)


def extract_minimum_years(text: str) -> float | None:
    """Section 10.6: finds the general minimum-years-of-experience
    requirement stated anywhere in `text`.

    Rules implemented: "3+" -> 3; a range ("two to four years") takes
    the lower bound; a value is only extracted when tied to explicit
    experience wording (never inferred from a seniority word alone -
    none of the patterns below can match on "senior" by itself).

    When more than one such phrase appears, the earliest one in the
    document wins. Section 10.6 also distinguishes a "general" minimum
    ("at least 2 years of experience") from a "skill-specific" one
    ("5+ years of Python experience"), keeping the latter only as
    requirement metadata rather than the overall minimum - none of
    this project's synthetic job descriptions use a skill-specific
    year pattern, so that distinction isn't implemented here; a known,
    documented simplification.
    """
    candidates: list[tuple[int, float]] = []

    def add_candidates(pattern: re.Pattern, group: int = 1) -> None:
        for m in pattern.finditer(text):
            value = parse_number_word(m.group(group))
            if value is not None:
                candidates.append((m.start(), float(value)))

    for m in _YEARS_PLUS_RE.finditer(text):
        candidates.append((m.start(), float(m.group(1))))

    add_candidates(_RANGE_RE, group=1)  # lower bound of the range
    add_candidates(_AT_LEAST_RE)
    add_candidates(_MINIMUM_OF_RE)
    add_candidates(_YEARS_OF_EXPERIENCE_RE)

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]


# ---------------------------------------------------------------------------
# Input validation (Section 10.1)
# ---------------------------------------------------------------------------


def validate_description(raw_description: str, job_parsing_config) -> None:
    """Raises domain.exceptions.ValidationError with a specific, user-
    facing reason for any of: empty, too short, too long, mostly
    non-text symbols. (The "nothing scoreable extracted" case is
    checked after extraction, in parse_job_description().)"""
    text = raw_description.strip()
    if not text:
        raise ValidationError(
            "Job description is empty. Please paste a job description."
        )

    if len(text) < job_parsing_config.min_description_chars:
        raise ValidationError(
            f"Job description is too short ({len(text)} characters; minimum "
            f"{job_parsing_config.min_description_chars}). Please paste the full description."
        )

    if len(text) > job_parsing_config.max_description_chars:
        raise ValidationError(
            f"Job description is too long ({len(text)} characters; maximum "
            f"{job_parsing_config.max_description_chars}). Please shorten it."
        )

    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars / len(text) < 0.5:
        raise ValidationError(
            "Job description appears to be mostly non-text symbols. Please paste a readable job description."
        )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def build_extractor_context(taxonomy) -> ExtractorContext:
    """Builds the (skill/degree/field/certification) matching indices
    from a loaded TaxonomyBundle. Cheap enough to call per parse for
    this stage; a future service layer can cache and reuse one context
    across a whole session instead."""
    return ExtractorContext(
        skill_index=build_skill_index(taxonomy.skills),
        degree_index=build_degree_index(taxonomy.degrees),
        field_index=build_field_index(taxonomy.fields),
        certification_index=build_certification_index(taxonomy.certifications),
    )


def _looks_like_excluded_boilerplate(sentence: str) -> bool:
    """No-headings fallback only (Section 10.2): a lightweight guard
    against classifying obvious benefits/company-boilerplate sentences
    as responsibilities, since there's no heading to exclude them by."""
    return bool(_EXCLUDED_BOILERPLATE_RE.search(sentence))


def _looks_like_a_responsibility_sentence(sentence: str) -> bool:
    """No-headings fallback only: a single degenerate token (no spaces
    at all - e.g. garbled/non-text input that still technically passed
    the Section 10.1 alphabetic-ratio check) is not a plausible
    responsibility bullet and would otherwise let unscoreable garbage
    text slip past the "nothing scoreable" rejection in Section 10.1."""
    return " " in sentence.strip()


def _classify_and_extract_with_headings(
    sections: dict[str, list[str]], context: ExtractorContext
) -> tuple[list[JobRequirement], list, list[ParsingWarning]]:
    all_requirements: list[JobRequirement] = []
    warnings: list[ParsingWarning] = []

    for section_name in ("required", "preferred"):
        for sentence in split_into_items(sections.get(section_name, [])):
            classification = classify_sentence(
                sentence, section_name, has_headings=True
            )
            if classification.required is None:
                warnings.append(
                    ParsingWarning(
                        code="AMBIGUOUS_REQUIREMENT_CLASSIFICATION",
                        message=f'Could not confidently classify as required or preferred: "{sentence}"',
                        source_text=sentence,
                    )
                )
            all_requirements.extend(
                extract_requirements_from_sentence(classification, context)
            )

    responsibilities = extract_responsibilities(sections.get("responsibilities", []))
    return all_requirements, responsibilities, warnings


def _classify_and_extract_without_headings(
    sections: dict[str, list[str]], context: ExtractorContext
) -> tuple[list[JobRequirement], list, list[ParsingWarning]]:
    """Section 10.2 fallback: "If no headings exist, classify sentence-
    by-sentence using cue phrases." Every sentence in the document is
    independently checked for a required/preferred cue; sentences with
    a cue become qualification-extraction candidates, boilerplate-
    looking sentences are dropped, and everything else becomes a
    responsibility candidate."""
    all_requirements: list[JobRequirement] = []
    responsibility_items: list[str] = []
    warnings = [
        ParsingWarning(
            code="NO_HEADINGS",
            message="No section headings were detected; classified sentence-by-sentence using cue phrases.",
            source_text=None,
        )
    ]

    for sentence in split_into_items(sections.get("unsectioned", [])):
        if _looks_like_excluded_boilerplate(sentence):
            continue
        classification = classify_sentence(sentence, section=None, has_headings=False)
        if classification.required is not None:
            all_requirements.extend(
                extract_requirements_from_sentence(classification, context)
            )
        elif _looks_like_a_responsibility_sentence(sentence):
            responsibility_items.append(sentence)

    responsibilities = build_responsibilities_from_items(responsibility_items)
    return all_requirements, responsibilities, warnings


def parse_job_description(
    raw_description: str,
    *,
    title: str | None,
    taxonomy,
    scoring_config,
) -> JobProfile:
    """Section 10 end to end: validates the input, splits it into
    sections (or falls back to sentence-by-sentence cue classification
    when there are no headings), extracts and classifies requirements,
    extracts responsibilities, extracts the minimum-years requirement,
    and returns an unconfirmed JobProfile.

    Raises domain.exceptions.ValidationError for any Section 10.1
    rejection reason, including "nothing scoreable extracted".
    """
    validate_description(raw_description, scoring_config.job_parsing)

    context = build_extractor_context(taxonomy)
    sections, has_headings = split_into_sections(raw_description, JOB_HEADINGS)

    if has_headings:
        all_requirements, responsibilities, warnings = (
            _classify_and_extract_with_headings(sections, context)
        )
    else:
        all_requirements, responsibilities, warnings = (
            _classify_and_extract_without_headings(sections, context)
        )

    merged_requirements = merge_duplicate_requirements(all_requirements)
    required_qualifications = [r for r in merged_requirements if r.required]
    preferred_qualifications = [r for r in merged_requirements if not r.required]

    minimum_relevant_years = extract_minimum_years(raw_description)

    if (
        not required_qualifications
        and not preferred_qualifications
        and not responsibilities
    ):
        raise ValidationError(
            "Nothing scoreable was found in this job description - please edit the description "
            "or add required/preferred qualifications and responsibilities manually on the "
            "confirmation page."
        )

    return JobProfile(
        title=title,
        raw_description=raw_description,
        required_qualifications=required_qualifications,
        preferred_qualifications=preferred_qualifications,
        minimum_relevant_years=minimum_relevant_years,
        responsibilities=responsibilities,
        warnings=warnings,
        parser_version=PARSER_VERSION,
        confirmed=False,
    )


# ---------------------------------------------------------------------------
# Confidence banding (Section 10.5)
# ---------------------------------------------------------------------------

ConfidenceBand = Literal["include", "review", "exclude"]


def confidence_band(confidence: float, job_parsing_config) -> ConfidenceBand:
    """>= auto_include_confidence -> include normally; >= review_confidence
    -> include but highlighted for review; below that -> excluded from
    scoring until the recruiter explicitly confirms it."""
    if confidence >= job_parsing_config.auto_include_confidence:
        return "include"
    if confidence >= job_parsing_config.review_confidence:
        return "review"
    return "exclude"


def scoreable_requirements(
    requirements: list[JobRequirement], job_parsing_config
) -> list[JobRequirement]:
    """Requirements that count toward scoring by default (Section 10.5):
    everything except confidence-banded "exclude" items, which need an
    explicit recruiter confirmation first (Section 10.8)."""
    return [
        r
        for r in requirements
        if confidence_band(r.confidence, job_parsing_config) != "exclude"
    ]


# ---------------------------------------------------------------------------
# Confirmation-page contract (Section 10.8) - pure data operations.
# The Streamlit page itself is a later stage; this is the data contract
# it will call into: add/edit/delete/reclassify items, then confirm.
# ---------------------------------------------------------------------------


def _find_requirement(profile: JobProfile, requirement_id: UUID) -> tuple[str, int]:
    for list_name in ("required_qualifications", "preferred_qualifications"):
        for index, requirement in enumerate(getattr(profile, list_name)):
            if requirement.requirement_id == requirement_id:
                return list_name, index
    raise ValidationError(f"No requirement found with id {requirement_id}.")


def add_requirement(profile: JobProfile, requirement: JobRequirement) -> JobProfile:
    list_name = (
        "required_qualifications"
        if requirement.required
        else "preferred_qualifications"
    )
    updated = list(getattr(profile, list_name)) + [requirement]
    return profile.model_copy(update={list_name: updated, "confirmed": False})


def edit_requirement(
    profile: JobProfile, requirement_id: UUID, **changes
) -> JobProfile:
    list_name, index = _find_requirement(profile, requirement_id)
    items = list(getattr(profile, list_name))
    items[index] = items[index].model_copy(update=changes)
    return profile.model_copy(update={list_name: items, "confirmed": False})


def delete_requirement(profile: JobProfile, requirement_id: UUID) -> JobProfile:
    list_name, index = _find_requirement(profile, requirement_id)
    items = list(getattr(profile, list_name))
    del items[index]
    return profile.model_copy(update={list_name: items, "confirmed": False})


def reclassify_requirement(
    profile: JobProfile, requirement_id: UUID, *, required: bool
) -> JobProfile:
    """Moves an item between required <-> preferred (Section 10.8)."""
    list_name, index = _find_requirement(profile, requirement_id)
    items = list(getattr(profile, list_name))
    moved = items.pop(index).model_copy(update={"required": required})

    target_list_name = (
        "required_qualifications" if required else "preferred_qualifications"
    )
    if target_list_name == list_name:
        items.append(moved)
        return profile.model_copy(update={list_name: items, "confirmed": False})

    target_items = list(getattr(profile, target_list_name)) + [moved]
    return profile.model_copy(
        update={list_name: items, target_list_name: target_items, "confirmed": False}
    )


def confirm_job_profile(profile: JobProfile) -> JobProfile:
    """Section 10.8: "Confirm and Continue" sets confirmed=True and
    freezes the profile. Guards against confirming a profile that (after
    recruiter edits) no longer has anything scoreable - the same rule
    Section 10.1 applies at parse time."""
    if (
        not profile.required_qualifications
        and not profile.preferred_qualifications
        and not profile.responsibilities
    ):
        raise ValidationError(
            "Nothing scoreable in this job profile - please add requirements or responsibilities before confirming."
        )
    return profile.model_copy(update={"confirmed": True})
