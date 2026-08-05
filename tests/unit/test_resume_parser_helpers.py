"""Unit tests for parsing/resume_parser.py's internal helpers."""

from __future__ import annotations

from parsing.resume_parser import (
    _is_fully_redacted,
    _looks_like_bare_skill_list,
    _recover_orphaned_table_content,
)


def test_fully_redacted_name_line_detected():
    assert _is_fully_redacted("[REDACTED]") is True


def test_partially_redacted_contact_line_not_fully_redacted():
    assert _is_fully_redacted("[REDACTED] | [REDACTED] | San Jose, CA") is False


def test_ordinary_line_not_flagged():
    assert _is_fully_redacted("Built dashboards for the team.") is False


def test_bare_skill_list_detected():
    assert _looks_like_bare_skill_list("SQL, Python, Data Pipelines") is True


def test_sentence_with_period_not_a_bare_list():
    assert _looks_like_bare_skill_list("Built dashboards for the team.") is False


def test_single_word_not_a_bare_list():
    assert _looks_like_bare_skill_list("SQL") is False


def test_recover_orphaned_table_content_moves_trailing_list():
    sections = {
        "skills": [],
        "education": [
            "Bachelor of Science in Information Systems, Willamette State University, completed.",
            "SQL, Python, Data Pipelines",
        ],
    }
    recovered = _recover_orphaned_table_content(sections)
    assert recovered["skills"] == ["SQL, Python, Data Pipelines"]
    assert recovered["education"] == [
        "Bachelor of Science in Information Systems, Willamette State University, completed."
    ]


def test_recover_orphaned_table_content_no_op_when_skills_already_populated():
    sections = {
        "skills": ["SQL, Python"],
        "education": ["Bachelor's degree, completed."],
    }
    assert _recover_orphaned_table_content(sections) == sections


def test_recover_orphaned_table_content_no_op_when_nothing_looks_like_a_list():
    sections = {"skills": [], "education": ["Bachelor's degree, completed."]}
    assert _recover_orphaned_table_content(sections) == sections
