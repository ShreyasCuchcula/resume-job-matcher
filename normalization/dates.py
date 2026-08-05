"""Employment date-range parsing (SPECIFICATION.md Section 9.7).

Lives in `normalization/` rather than `parsing/` per the Section 2.2
dependency rule (`parsing -> normalization -> domain`) and the Section
4 file listing (`normalization/dates.py # month/year parsing, Present,
intervals`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTH_NAMES: dict[str, int] = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PRESENT_WORDS = {"present", "current", "currently", "now", "ongoing"}

_RANGE_SEPARATOR_RE = re.compile(r"\s*[-–—]\s*")
_MONTH_YEAR_RE = re.compile(r"^([A-Za-z]+)\.?\s+(\d{4})$")
_NUMERIC_MONTH_YEAR_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_YEAR_ONLY_RE = re.compile(r"^(\d{4})$")


@dataclass(frozen=True)
class ParsedDate:
    value: date
    is_year_only: bool


@dataclass(frozen=True)
class DateRangeResult:
    start_date: date | None
    end_date: date | None
    is_current: bool
    date_confidence: float
    warning_code: (
        str | None
    )  # "YEAR_ONLY_DATE" | "INVALID_DATE_RANGE" | "MISSING_DATES" | None


def is_present_word(token: str) -> bool:
    return token.strip().lower() in PRESENT_WORDS


def parse_single_date(token: str, *, is_start: bool) -> ParsedDate | None:
    """Parses one side of a date range. `is_start` controls year-only
    resolution: Jan 1 for a start date, Dec 31 for an end date
    (Section 9.7). Month-precision dates always resolve to day 1 -
    duration math at day-of-month precision isn't a Stage 4 concern."""
    token = token.strip()
    if not token:
        return None

    m = _MONTH_YEAR_RE.match(token)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        if month is not None:
            return ParsedDate(date(int(m.group(2)), month, 1), is_year_only=False)

    m = _NUMERIC_MONTH_YEAR_RE.match(token)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12:
            return ParsedDate(date(int(m.group(2)), month, 1), is_year_only=False)

    m = _YEAR_ONLY_RE.match(token)
    if m:
        year = int(m.group(1))
        return ParsedDate(
            date(year, 1, 1) if is_start else date(year, 12, 31), is_year_only=True
        )

    return None


def parse_date_range(text: str, run_date: date) -> DateRangeResult:
    """Section 9.7 end to end. `run_date` stands in for "the scoring
    run date" used as the effective end date for a "Present" role -
    that effective value isn't stored here (end_date stays None for an
    ongoing role; Stage 7's duration math is what actually needs
    `run_date`), but computing it up front is how INVALID_DATE_RANGE
    gets detected for a "Present" role whose start is implausibly late.
    """
    text = text.strip()
    if not text:
        return DateRangeResult(None, None, False, 0.0, "MISSING_DATES")

    parts = _RANGE_SEPARATOR_RE.split(text, maxsplit=1)
    if len(parts) != 2:
        return DateRangeResult(None, None, False, 0.0, "MISSING_DATES")

    start_token, end_token = parts[0].strip(), parts[1].strip()
    is_current = is_present_word(end_token)

    start = parse_single_date(start_token, is_start=True)
    end = None if is_current else parse_single_date(end_token, is_start=False)

    if start is None or (not is_current and end is None):
        return DateRangeResult(None, None, False, 0.0, "MISSING_DATES")

    year_only = start.is_year_only or (end.is_year_only if end is not None else False)
    confidence = 0.6 if year_only else 1.0

    effective_end = run_date if is_current else end.value
    if effective_end < start.value:
        return DateRangeResult(None, None, False, 0.0, "INVALID_DATE_RANGE")

    return DateRangeResult(
        start_date=start.value,
        end_date=None if is_current else end.value,
        is_current=is_current,
        date_confidence=confidence,
        warning_code="YEAR_ONLY_DATE" if year_only else None,
    )
