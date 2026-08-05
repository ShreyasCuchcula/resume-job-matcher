"""Unit tests for parsing/job_parser.py's minimum-years extraction
(SPECIFICATION.md Section 10.6, Section 18.1 fixtures)."""

from __future__ import annotations

from pathlib import Path

from parsing.job_parser import extract_minimum_years

SAMPLE_JOBS_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data" / "jobs"


def test_plus_pattern():
    assert extract_minimum_years("3+ years") == 3.0


def test_at_least_written_number():
    assert extract_minimum_years("at least three years") == 3.0


def test_minimum_of_pattern():
    assert extract_minimum_years("minimum of 2 years") == 2.0


def test_range_takes_lower_bound():
    """Section 18.1 fixture: "two to four years" -> 2.0."""
    assert extract_minimum_years("two to four years") == 2.0


def test_years_of_relevant_experience_pattern():
    assert extract_minimum_years("5 years of relevant experience") == 5.0


def test_senior_alone_yields_no_minimum():
    """Section 18.1 fixture: "senior" alone yields no minimum."""
    assert (
        extract_minimum_years("Senior Data Analyst with strong leadership skills.")
        is None
    )
    assert (
        extract_minimum_years("We are looking for a senior, experienced candidate.")
        is None
    )


def test_no_mention_of_years_yields_none():
    assert extract_minimum_years("Must have strong SQL skills.") is None


def test_earliest_mention_wins_when_multiple_present():
    text = "Candidates must have at least 2 years of experience. Also 5 years of relevant experience preferred."
    assert extract_minimum_years(text) == 2.0


def test_equivalent_experience_years_not_mistaken_for_general_minimum():
    """ "...or equivalent experience of 4 years..." must not be picked up
    by the general minimum-years scanner (word order is reversed:
    "experience of N years", not "N years of experience")."""
    text = "A master's degree or equivalent experience of 4 years is required."
    assert extract_minimum_years(text) is None


def test_all_six_synthetic_jobs_match_expected_minimums():
    expected = {
        "job_01_data_analyst_standard.txt": 2.0,
        "job_02_data_analyst_altheadings.txt": 3.0,
        "job_03_data_engineer.txt": 3.0,
        "job_04_bi_analyst.txt": None,
        "job_05_data_scientist.txt": 2.0,
        "job_06_software_engineer.txt": 2.0,
    }
    for filename, expected_min in expected.items():
        text = (SAMPLE_JOBS_DIR / filename).read_text(encoding="utf-8")
        assert extract_minimum_years(text) == expected_min, filename
