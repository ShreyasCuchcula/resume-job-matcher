"""Unit tests for parsing/requirement_extractor.py (SPECIFICATION.md
Section 10.3, 10.4, 10.5, and the Section 18.1 fixtures)."""

from __future__ import annotations

import json

import pytest

from domain.schemas import JobRequirement
from parsing.certification_extractor import build_certification_index
from parsing.education_extractor import build_degree_index, build_field_index
from parsing.requirement_extractor import (
    ExtractorContext,
    classify_sentence,
    compute_confidence,
    compute_importance,
    extract_requirements_from_sentence,
    merge_duplicate_requirements,
)
from parsing.skill_extractor import build_skill_index

REPO_ROOT_CONFIG = "config/taxonomy"


@pytest.fixture(scope="module")
def context() -> ExtractorContext:
    skills = json.load(open(f"{REPO_ROOT_CONFIG}/skills.json", encoding="utf-8"))
    degrees = json.load(open(f"{REPO_ROOT_CONFIG}/degrees.json", encoding="utf-8"))
    fields = json.load(open(f"{REPO_ROOT_CONFIG}/fields.json", encoding="utf-8"))
    certs = json.load(open(f"{REPO_ROOT_CONFIG}/certifications.json", encoding="utf-8"))
    return ExtractorContext(
        skill_index=build_skill_index(skills),
        degree_index=build_degree_index(degrees),
        field_index=build_field_index(fields),
        certification_index=build_certification_index(certs),
    )


# ---------------------------------------------------------------------------
# Section 10.3 classification
# ---------------------------------------------------------------------------


def test_explicit_required_cue_classifies_required_regardless_of_section():
    result = classify_sentence(
        "Must have SQL experience.", section="required", has_headings=True
    )
    assert result.required is True
    assert "must have" in result.matched_cues


def test_explicit_preferred_cue_classifies_preferred():
    result = classify_sentence("Python is a plus.", section=None, has_headings=False)
    assert result.required is False
    assert "a plus" in result.matched_cues


def test_wording_beats_heading_python_preferred_inside_requirements_section():
    """Section 18.1 fixture: "Python is preferred" inside a Requirements
    section is still classified preferred - explicit sentence wording
    beats the section heading (Section 10.3 priority rule)."""
    result = classify_sentence(
        "Python is preferred.", section="required", has_headings=True
    )
    assert result.required is False
    assert "preferred" in result.matched_cues


def test_heading_used_when_sentence_has_no_explicit_cue():
    result = classify_sentence(
        "Experience with SQL databases.", section="required", has_headings=True
    )
    assert result.required is True
    assert result.matched_cues == ()


def test_ambiguous_when_no_cue_and_no_heading_section():
    result = classify_sentence(
        "Experience with SQL databases.", section=None, has_headings=False
    )
    assert result.required is None


# ---------------------------------------------------------------------------
# Section 10.4 importance
# ---------------------------------------------------------------------------


def test_importance_strong_required_cue_is_3():
    assert compute_importance(True, ("must have",)) == 3
    assert compute_importance(True, ("required",)) == 3
    assert compute_importance(True, ("essential",)) == 3


def test_importance_standard_required_membership_is_2():
    assert compute_importance(True, ()) == 2
    assert compute_importance(True, ("minimum of",)) == 2


def test_importance_standard_preferred_cue_is_2():
    assert compute_importance(False, ("preferred",)) == 2
    assert compute_importance(False, ("desired",)) == 2


def test_importance_weak_preferred_cue_is_1():
    assert compute_importance(False, ("a plus",)) == 1
    assert compute_importance(False, ("nice to have",)) == 1
    assert compute_importance(False, ("familiarity with",)) == 1


# ---------------------------------------------------------------------------
# Section 10.5 confidence
# ---------------------------------------------------------------------------


def test_confidence_base_plus_taxonomy_match_only():
    # 0.30 base + 0.25 taxonomy match, no cue/heading/pattern bonus
    assert (
        compute_confidence(has_cue=False, from_heading=False, exact_pattern_bonus=False)
        == 0.55
    )


def test_confidence_all_bonuses_clamped_to_one():
    # 0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.00
    assert (
        compute_confidence(has_cue=True, from_heading=True, exact_pattern_bonus=True)
        == 1.00
    )


def test_confidence_skill_with_cue_and_heading_no_pattern_bonus():
    # 0.30 + 0.25 + 0.20 + 0.15 = 0.90 (skills never get the +0.10 exact-pattern bonus)
    assert (
        compute_confidence(has_cue=True, from_heading=True, exact_pattern_bonus=False)
        == 0.90
    )


# ---------------------------------------------------------------------------
# End-to-end extraction fixtures (Section 18.1)
# ---------------------------------------------------------------------------


def test_must_have_sql_extracts_required_sql_importance_3(context):
    classification = classify_sentence(
        "Must have SQL.", section="required", has_headings=True
    )
    items = extract_requirements_from_sentence(classification, context)
    sql_items = [i for i in items if i.canonical_name == "sql"]
    assert len(sql_items) == 1
    assert sql_items[0].required is True
    assert sql_items[0].importance == 3
    assert sql_items[0].type == "skill"


def test_python_is_a_plus_extracts_preferred_python(context):
    classification = classify_sentence(
        "Python is a plus.", section="preferred", has_headings=True
    )
    items = extract_requirements_from_sentence(classification, context)
    python_items = [i for i in items if i.canonical_name == "python"]
    assert len(python_items) == 1
    assert python_items[0].required is False
    assert python_items[0].importance == 1


def test_python_is_preferred_inside_requirements_section_extracts_preferred(context):
    """The full pipeline version of the wording-beats-heading fixture:
    even though the section is "required", the extracted item is
    preferred because the sentence itself says "preferred"."""
    classification = classify_sentence(
        "Python is preferred.", section="required", has_headings=True
    )
    items = extract_requirements_from_sentence(classification, context)
    python_items = [i for i in items if i.canonical_name == "python"]
    assert len(python_items) == 1
    assert python_items[0].required is False


def test_sentence_with_no_taxonomy_terms_extracts_nothing(context):
    classification = classify_sentence(
        "Health insurance, 401k matching, and unlimited PTO.",
        section="excluded",
        has_headings=True,
    )
    items = extract_requirements_from_sentence(classification, context)
    assert items == []


def test_education_item_carries_degree_and_field(context):
    classification = classify_sentence(
        "A bachelor's degree in Computer Science is required.",
        section="required",
        has_headings=True,
    )
    items = extract_requirements_from_sentence(classification, context)
    edu_items = [i for i in items if i.type == "education"]
    assert len(edu_items) == 1
    assert edu_items[0].degree_level == "bachelor"
    assert edu_items[0].field_of_study == "computer science"
    assert edu_items[0].importance == 3  # "required" is a strong cue


def test_equivalent_experience_clause_sets_flag_and_years(context):
    classification = classify_sentence(
        "A master's degree in Statistics, or equivalent experience of 4 years, is required.",
        section="required",
        has_headings=True,
    )
    items = extract_requirements_from_sentence(classification, context)
    edu_items = [i for i in items if i.type == "education"]
    assert len(edu_items) == 1
    assert edu_items[0].allows_equivalent_experience is True
    assert edu_items[0].equivalent_years == 4.0


def test_equivalent_experience_without_stated_years_never_invents_a_number(context):
    classification = classify_sentence(
        "A bachelor's degree or equivalent experience is required.",
        section="required",
        has_headings=True,
    )
    items = extract_requirements_from_sentence(classification, context)
    edu_items = [i for i in items if i.type == "education"]
    assert edu_items[0].allows_equivalent_experience is True
    assert edu_items[0].equivalent_years is None


# ---------------------------------------------------------------------------
# Duplicate merging
# ---------------------------------------------------------------------------


def _skill_requirement(
    canonical_name: str, required: bool, importance: int, confidence: float
) -> JobRequirement:
    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text="x",
        importance=importance,
        confidence=confidence,
        required=required,
    )


def test_merge_duplicates_keeps_highest_importance():
    items = [
        _skill_requirement("sql", required=True, importance=1, confidence=0.6),
        _skill_requirement("sql", required=True, importance=3, confidence=0.9),
        _skill_requirement("sql", required=True, importance=2, confidence=0.7),
    ]
    merged = merge_duplicate_requirements(items)
    assert len(merged) == 1
    assert merged[0].importance == 3


def test_merge_duplicates_required_beats_preferred_on_tie():
    items = [
        _skill_requirement("python", required=False, importance=2, confidence=0.9),
        _skill_requirement("python", required=True, importance=2, confidence=0.9),
    ]
    merged = merge_duplicate_requirements(items)
    assert len(merged) == 1
    assert merged[0].required is True


def test_merge_duplicates_preserves_distinct_items():
    items = [
        _skill_requirement("sql", required=True, importance=3, confidence=0.9),
        _skill_requirement("python", required=False, importance=1, confidence=0.6),
    ]
    merged = merge_duplicate_requirements(items)
    assert len(merged) == 2
