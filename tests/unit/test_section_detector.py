"""Unit tests for parsing/section_detector.py (SPECIFICATION.md Section
9.1, Section 10.2)."""

from __future__ import annotations

from parsing.section_detector import (
    JOB_HEADINGS,
    RESUME_HEADINGS,
    detect_heading,
    normalize_heading_text,
    split_into_sections,
)


def test_normalize_heading_text_strips_punctuation_and_case():
    assert normalize_heading_text("Requirements:") == "requirements"
    assert normalize_heading_text("  Responsibilities  ") == "responsibilities"
    assert (
        normalize_heading_text("PREFERRED QUALIFICATIONS") == "preferred qualifications"
    )


def test_detect_heading_matches_job_headings_case_insensitively():
    assert detect_heading("Requirements", JOB_HEADINGS) == "required"
    assert detect_heading("requirements", JOB_HEADINGS) == "required"
    assert detect_heading("REQUIREMENTS:", JOB_HEADINGS) == "required"
    assert detect_heading("What You Will Do", JOB_HEADINGS) == "responsibilities"
    assert detect_heading("Nice to Have", JOB_HEADINGS) == "preferred"
    assert detect_heading("Benefits", JOB_HEADINGS) == "excluded"


def test_detect_heading_returns_none_for_non_heading_content():
    assert (
        detect_heading("Must have strong SQL skills, including joins.", JOB_HEADINGS)
        is None
    )
    assert (
        detect_heading("random prose that is not a heading at all here", JOB_HEADINGS)
        is None
    )


def test_detect_heading_rejects_long_lines_even_if_they_contain_heading_words():
    long_line = "Requirements for this role include a strong understanding of SQL and Excel skills"
    assert detect_heading(long_line, JOB_HEADINGS) is None


def test_split_into_sections_standard_headings():
    text = """Data Analyst

About Us
We build things.

Responsibilities
- Build dashboards.
- Write SQL queries.

Requirements
- Must have SQL.

Preferred Qualifications
- Power BI is preferred.
"""
    sections, has_headings = split_into_sections(text, JOB_HEADINGS)
    assert has_headings is True
    assert sections["excluded"] == ["We build things."]
    assert sections["responsibilities"] == [
        "- Build dashboards.",
        "- Write SQL queries.",
    ]
    assert sections["required"] == ["- Must have SQL."]
    assert sections["preferred"] == ["- Power BI is preferred."]
    assert sections["unsectioned"] == ["Data Analyst"]


def test_split_into_sections_no_headings_reports_false():
    text = "Just some plain text with no section headings at all in it."
    sections, has_headings = split_into_sections(text, JOB_HEADINGS)
    assert has_headings is False
    assert sections["unsectioned"] == [text]


def test_resume_headings_present_for_future_use():
    assert RESUME_HEADINGS["professional experience"] == "experience"
    assert RESUME_HEADINGS["skills"] == "skills"
    assert RESUME_HEADINGS["interests"] == "excluded"
