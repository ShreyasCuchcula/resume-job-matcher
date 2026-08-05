"""Unit tests for parsing/employment_extractor.py (SPECIFICATION.md
Section 9.7)."""

from __future__ import annotations

from datetime import date

from normalization.titles import build_title_lookup
from parsing.employment_extractor import (
    extract_employment_records,
    parse_role_header,
    split_experience_into_role_blocks,
)

RUN_DATE = date(2026, 8, 1)
TITLE_LOOKUP = build_title_lookup(
    {
        "data analyst": {"aliases": [], "related_titles": []},
        "reporting analyst": {"aliases": [], "related_titles": []},
    }
)


def test_parse_role_header_with_dates():
    title, company, dates = parse_role_header(
        "Data Analyst - Acme Corp (Jan 2020 - Present)"
    )
    assert title == "Data Analyst"
    assert company == "Acme Corp"
    assert dates == "Jan 2020 - Present"


def test_parse_role_header_without_dates():
    title, company, dates = parse_role_header("Data Analyst - Acme Corp")
    assert title == "Data Analyst"
    assert company == "Acme Corp"
    assert dates is None


def test_parse_role_header_unparseable_returns_all_none():
    assert parse_role_header("Not a header at all") == (None, None, None)


def test_split_into_role_blocks_basic():
    lines = [
        "Data Analyst - Acme Corp (Jan 2020 - Present)",
        "- Built dashboards.",
        "- Wrote SQL.",
        "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)",
        "- Built reports.",
    ]
    blocks = split_experience_into_role_blocks(lines)
    assert len(blocks) == 2
    assert blocks[0].header_line == "Data Analyst - Acme Corp (Jan 2020 - Present)"
    assert blocks[0].bullet_lines == ["- Built dashboards.", "- Wrote SQL."]
    assert blocks[1].header_line == "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)"


def test_split_into_role_blocks_wrapped_bullet_stays_with_previous_role():
    """A bullet wrapped across two physical lines must not be mistaken
    for a new role header, even though it's a non-bulleted line
    immediately following bulleted content."""
    lines = [
        "Data Analyst - Acme Corp (Jan 2020 - Present)",
        "- Wrote SQL queries against the warehouse, including joins, to",
        "answer ad hoc business questions.",
        "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)",
        "- Built reports.",
    ]
    blocks = split_experience_into_role_blocks(lines)
    assert len(blocks) == 2
    assert blocks[0].bullet_lines == [
        "- Wrote SQL queries against the warehouse, including joins, to",
        "answer ad hoc business questions.",
    ]
    assert blocks[1].header_line == "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)"


def test_split_into_role_blocks_role_with_zero_bullets():
    lines = [
        "Data Analyst - Acme Corp (Jan 2020 - Present)",
        "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)",
        "- Built reports.",
    ]
    blocks = split_experience_into_role_blocks(lines)
    assert len(blocks) == 2
    assert blocks[0].bullet_lines == []


def test_extract_employment_records_full_pipeline():
    lines = [
        "Data Analyst - Acme Corp (Jan 2020 - Present)",
        "- Built dashboards.",
        "- Wrote SQL queries.",
    ]
    records, bullets, warnings = extract_employment_records(
        lines, title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert len(records) == 1
    record = records[0]
    assert record.original_title == "Data Analyst"
    assert record.normalized_title == "data analyst"
    assert record.company == "Acme Corp"
    assert record.start_date == date(2020, 1, 1)
    assert record.is_current is True
    assert record.date_confidence == 1.0
    assert len(bullets) == 2
    assert all(b.employment_id == record.employment_id for b in bullets)
    assert warnings == []


def test_extract_employment_records_missing_dates_warning():
    lines = ["Data Analyst - Acme Corp", "- Built dashboards."]
    records, _, warnings = extract_employment_records(
        lines, title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert records[0].start_date is None
    assert records[0].date_confidence == 0.0
    assert any(w.code == "MISSING_DATES" for w in warnings)


def test_extract_employment_records_year_only_warning():
    lines = ["Data Analyst - Acme Corp (2019 - 2022)", "- Built dashboards."]
    records, _, warnings = extract_employment_records(
        lines, title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert records[0].date_confidence == 0.6
    assert any(w.code == "YEAR_ONLY_DATE" for w in warnings)


def test_extract_employment_records_invalid_range_warning():
    lines = ["Data Analyst - Acme Corp (Mar 2023 - Jan 2020)", "- Built dashboards."]
    records, _, warnings = extract_employment_records(
        lines, title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert records[0].start_date is None
    assert records[0].end_date is None
    assert any(w.code == "INVALID_DATE_RANGE" for w in warnings)


def test_extract_employment_records_never_crashes_on_empty_input():
    records, bullets, warnings = extract_employment_records(
        [], title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert records == []
    assert bullets == []
    assert warnings == []


def test_multiple_roles_get_independent_employment_ids():
    lines = [
        "Data Analyst - Acme Corp (Jan 2020 - Dec 2021)",
        "- Built dashboards.",
        "Reporting Analyst - Beta Inc (Jan 2018 - Dec 2019)",
        "- Built reports.",
    ]
    records, bullets, _ = extract_employment_records(
        lines, title_lookup=TITLE_LOOKUP, run_date=RUN_DATE
    )
    assert len(records) == 2
    assert records[0].employment_id != records[1].employment_id
    bullet_employment_ids = {b.employment_id for b in bullets}
    assert bullet_employment_ids == {records[0].employment_id, records[1].employment_id}
