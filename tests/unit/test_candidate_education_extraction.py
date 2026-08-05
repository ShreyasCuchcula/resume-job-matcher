"""Unit tests for resume-side education extraction (SPECIFICATION.md
Section 9.5)."""

from __future__ import annotations

from parsing.education_extractor import (
    build_degree_index,
    build_field_index,
    determine_completion_status,
    extract_candidate_education,
)

DEGREES_TAXONOMY = {
    "levels": {
        "bachelor": {"aliases": ["bachelor's degree", "bachelor of science", "bs"]},
        "master": {"aliases": ["master's degree", "ms"]},
    }
}
FIELDS_TAXONOMY = {
    "computer science": {"related": [], "somewhat_related": []},
    "data analytics": {"related": [], "somewhat_related": []},
}


def _indices():
    return build_degree_index(DEGREES_TAXONOMY), build_field_index(FIELDS_TAXONOMY)


def test_completed_degree_extracted():
    degree_index, field_index = _indices()
    records = extract_candidate_education(
        ["Bachelor of Science in Data Analytics, State University, completed."],
        degree_index,
        field_index,
    )
    assert len(records) == 1
    assert records[0].degree_level == "bachelor"
    assert records[0].field_of_study == "data analytics"
    assert records[0].completed is True


def test_no_graduation_year_field_exists_on_the_record():
    """Section 9.4/9.5: no graduation year stored, ever (age proxy)."""
    degree_index, field_index = _indices()
    records = extract_candidate_education(
        ["Bachelor of Science in Computer Science, Tech University, 2019, completed."],
        degree_index,
        field_index,
    )
    assert not hasattr(records[0], "graduation_year")
    assert "graduation_year" not in records[0].model_dump()


def test_in_progress_degree_marked_not_completed():
    degree_index, field_index = _indices()
    records = extract_candidate_education(
        ["Master's Degree in Computer Science, expected 2027."],
        degree_index,
        field_index,
    )
    assert records[0].completed is False


def test_unclear_completion_status_returns_none():
    assert (
        determine_completion_status(
            "Bachelor of Science in Computer Science, Tech University"
        )
        is None
    )


def test_no_degree_mention_yields_no_records():
    degree_index, field_index = _indices()
    records = extract_candidate_education(
        ["Some college coursework in mathematics; no degree conferred."],
        degree_index,
        field_index,
    )
    assert records == []


def test_duplicate_degree_mentions_deduplicated():
    degree_index, field_index = _indices()
    records = extract_candidate_education(
        [
            "Bachelor of Science in Computer Science, Tech University, completed.",
            "Bachelor of Science in Computer Science, Tech University, completed.",
        ],
        degree_index,
        field_index,
    )
    assert len(records) == 1
