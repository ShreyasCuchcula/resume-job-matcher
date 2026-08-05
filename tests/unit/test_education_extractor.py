"""Unit tests for parsing/education_extractor.py (SPECIFICATION.md
Section 9.5, Section 10.4, Section 11.3)."""

from __future__ import annotations

from parsing.education_extractor import (
    build_degree_index,
    build_field_index,
    extract_education,
    find_equivalent_experience_clause,
)

DEGREES_TAXONOMY = {
    "levels": {
        "bachelor": {"aliases": ["bachelor's degree", "bs", "b.s."]},
        "master": {"aliases": ["master's degree", "ms", "m.s."]},
    }
}
FIELDS_TAXONOMY = {
    "computer science": {"related": [], "somewhat_related": []},
    "statistics": {"related": [], "somewhat_related": []},
    "data analytics": {"related": [], "somewhat_related": []},
}


def test_extract_education_finds_degree_and_field():
    degree_index = build_degree_index(DEGREES_TAXONOMY)
    field_index = build_field_index(FIELDS_TAXONOMY)
    result = extract_education(
        "A bachelor's degree in Computer Science is required.",
        degree_index,
        field_index,
    )
    assert result.degree_level == "bachelor"
    assert result.field_of_study == "computer science"


def test_extract_education_first_field_among_alternatives():
    degree_index = build_degree_index(DEGREES_TAXONOMY)
    field_index = build_field_index(FIELDS_TAXONOMY)
    result = extract_education(
        "A master's degree in a quantitative field such as Statistics, Computer Science, or Data Analytics.",
        degree_index,
        field_index,
    )
    assert result.degree_level == "master"
    assert result.field_of_study == "statistics"


def test_extract_education_returns_none_without_a_degree_mention():
    degree_index = build_degree_index(DEGREES_TAXONOMY)
    field_index = build_field_index(FIELDS_TAXONOMY)
    result = extract_education(
        "Strong SQL skills are required.", degree_index, field_index
    )
    assert result is None


def test_bare_short_abbreviation_requires_capitalization():
    degree_index = build_degree_index(DEGREES_TAXONOMY)
    field_index = build_field_index(FIELDS_TAXONOMY)
    # lowercase "bs" should never match (too ambiguous with ordinary text)
    result = extract_education(
        "as needed, bs is not a real word here", degree_index, field_index
    )
    assert result is None
    # but capitalized "BS" should match
    result = extract_education(
        "BS in Computer Science required.", degree_index, field_index
    )
    assert result is not None
    assert result.degree_level == "bachelor"


def test_equivalent_experience_clause_with_years():
    allows, years = find_equivalent_experience_clause(
        "or equivalent experience of 4 years, is required"
    )
    assert allows is True
    assert years == 4.0


def test_equivalent_experience_clause_with_written_number():
    allows, years = find_equivalent_experience_clause(
        "or equivalent experience of four years"
    )
    assert allows is True
    assert years == 4.0


def test_equivalent_experience_clause_without_years_never_invents_a_number():
    allows, years = find_equivalent_experience_clause(
        "a degree or equivalent experience is required"
    )
    assert allows is True
    assert years is None


def test_no_equivalent_experience_clause():
    allows, years = find_equivalent_experience_clause(
        "A bachelor's degree is required."
    )
    assert allows is False
    assert years is None
