"""Unit tests for normalization/dates.py (SPECIFICATION.md Section 9.7)."""

from __future__ import annotations

from datetime import date

from normalization.dates import parse_date_range, parse_single_date

RUN_DATE = date(2026, 8, 1)


def test_month_name_year_format():
    result = parse_date_range("Jan 2020 – Mar 2023", RUN_DATE)
    assert result.start_date == date(2020, 1, 1)
    assert result.end_date == date(2023, 3, 1)
    assert result.date_confidence == 1.0
    assert result.warning_code is None


def test_numeric_month_year_format():
    result = parse_date_range("01/2020 - 03/2023", RUN_DATE)
    assert result.start_date == date(2020, 1, 1)
    assert result.end_date == date(2023, 3, 1)
    assert result.date_confidence == 1.0


def test_year_only_format_resolves_jan1_dec31_and_lowers_confidence():
    result = parse_date_range("2020–2023", RUN_DATE)
    assert result.start_date == date(2020, 1, 1)
    assert result.end_date == date(2023, 12, 31)
    assert result.date_confidence == 0.6
    assert result.warning_code == "YEAR_ONLY_DATE"


def test_present_sets_is_current_and_none_end_date():
    result = parse_date_range("Jun 2022 - Present", RUN_DATE)
    assert result.is_current is True
    assert result.end_date is None
    assert result.start_date == date(2022, 6, 1)
    assert result.date_confidence == 1.0


def test_current_and_now_also_recognized_as_present():
    assert parse_date_range("Jan 2020 - Current", RUN_DATE).is_current is True
    assert parse_date_range("Jan 2020 - Ongoing", RUN_DATE).is_current is True


def test_year_only_present_still_lowers_confidence():
    result = parse_date_range("2019 - Present", RUN_DATE)
    assert result.is_current is True
    assert result.date_confidence == 0.6
    assert result.warning_code == "YEAR_ONLY_DATE"


def test_end_before_start_discards_interval():
    """Section 9.7: end before start -> discard interval + warning, never crash."""
    result = parse_date_range("Mar 2023 - Jan 2020", RUN_DATE)
    assert result.start_date is None
    assert result.end_date is None
    assert result.warning_code == "INVALID_DATE_RANGE"


def test_empty_text_is_missing_dates():
    result = parse_date_range("", RUN_DATE)
    assert result.warning_code == "MISSING_DATES"
    assert result.start_date is None


def test_unparseable_text_is_missing_dates_never_crashes():
    result = parse_date_range("garbled nonsense text", RUN_DATE)
    assert result.warning_code == "MISSING_DATES"
    assert result.start_date is None


def test_single_date_start_vs_end_year_only_resolution():
    start = parse_single_date("2020", is_start=True)
    end = parse_single_date("2020", is_start=False)
    assert start.value == date(2020, 1, 1)
    assert end.value == date(2020, 12, 31)
    assert start.is_year_only and end.is_year_only


def test_single_date_invalid_token_returns_none():
    assert parse_single_date("not a date", is_start=True) is None
    assert parse_single_date("", is_start=True) is None
