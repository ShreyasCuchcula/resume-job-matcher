"""Employment extraction: role-block splitting, title normalization,
date parsing (SPECIFICATION.md Section 9.7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from domain.schemas import EmploymentRecord, EvidenceBullet, ParsingWarning
from normalization.dates import DateRangeResult, parse_date_range
from normalization.titles import normalize_title
from parsing.common import is_bulleted, strip_bullet_prefix
from parsing.responsibility_extractor import extract_evidence_bullets

# "Title - Company (Dates)"; the dates group is optional (job3_missing_dates_engineer
# has no parens at all when dates weren't stated).
_HEADER_RE = re.compile(
    r"^(?P<title>.+?)\s-\s(?P<company>.+?)(?:\s\((?P<dates>[^)]+)\))?$"
)

_MISSING_DATES_RESULT = DateRangeResult(None, None, False, 0.0, "MISSING_DATES")


@dataclass(frozen=True)
class RoleBlock:
    header_line: str
    bullet_lines: list[str]


def _looks_like_role_header(line: str) -> bool:
    return _HEADER_RE.match(line.strip()) is not None


def split_experience_into_role_blocks(lines: list[str]) -> list[RoleBlock]:
    """A non-bulleted line starts a new role block (its header line);
    every bulleted line up to the next non-bulleted line belongs to
    that block (Section 9.7).

    A bullet that wraps across two physical lines (the same PDF-line-
    wrap pattern fixed for job parsing in Stage 3) produces a
    non-bulleted continuation line right where a new header could also
    legitimately appear - e.g. one role's last bullet is immediately
    followed by the next role's header line. These are disambiguated
    by shape: a non-bulleted line only starts a new block if it
    actually looks like "Title - Company (Dates)"; otherwise, while
    still inside a bullet's content, it's treated as that bullet's
    wrapped continuation.
    """
    blocks: list[RoleBlock] = []
    current_header: str | None = None
    current_lines: list[str] = []
    in_bullet_content = False

    for line in lines:
        if is_bulleted(line):
            current_lines.append(line)
            in_bullet_content = True
        elif in_bullet_content and not _looks_like_role_header(line):
            current_lines.append(line)  # wrapped continuation of the previous bullet
        else:
            if current_header is not None:
                blocks.append(RoleBlock(current_header, current_lines))
            current_header = line
            current_lines = []
            in_bullet_content = False

    if current_header is not None:
        blocks.append(RoleBlock(current_header, current_lines))

    return blocks


def parse_role_header(header_line: str) -> tuple[str | None, str | None, str | None]:
    """Returns (title, company, dates_text). Any of the three may be
    None if the header doesn't match the expected "Title - Company
    (Dates)" shape - the whole line is then kept as `original_title`
    by the caller rather than discarded."""
    match = _HEADER_RE.match(header_line.strip())
    if not match:
        return None, None, None
    dates_text = (match.group("dates") or "").strip() or None
    return match.group("title").strip(), match.group("company").strip(), dates_text


def _warning_for(code: str, dates_text: str | None, header_line: str) -> ParsingWarning:
    messages = {
        "YEAR_ONLY_DATE": (
            f'Date range "{dates_text}" only specifies years; resolved to Jan 1 / Dec 31 '
            f"internally and date confidence lowered to 0.6."
        ),
        "INVALID_DATE_RANGE": f'End date is before the start date in "{dates_text}"; this interval was discarded.',
        "MISSING_DATES": f'Could not parse dates for "{header_line}"; experience years may be underestimated.',
    }
    return ParsingWarning(code=code, message=messages[code], source_text=header_line)


def extract_employment_records(
    experience_lines: list[str],
    *,
    title_lookup: dict[str, str],
    run_date: date,
    phrase_map: dict[str, str] | None = None,
) -> tuple[list[EmploymentRecord], list[EvidenceBullet], list[ParsingWarning]]:
    """Section 9.7 end to end: splits the experience section into role
    blocks, parses each header into title/company/dates, normalizes
    the title, parses the date range (Jan-1/Dec-31 resolution and
    confidence lowering for year-only dates, discarding an inverted
    range, flagging missing dates - never crashing), and builds that
    role's evidence bullets linked to its EmploymentRecord.
    """
    records: list[EmploymentRecord] = []
    bullets: list[EvidenceBullet] = []
    warnings: list[ParsingWarning] = []

    for block in split_experience_into_role_blocks(experience_lines):
        title, company, dates_text = parse_role_header(block.header_line)
        if title is None:
            title = (
                block.header_line
            )  # unparsed header: keep the whole line as a fallback

        date_result = (
            parse_date_range(dates_text, run_date)
            if dates_text
            else _MISSING_DATES_RESULT
        )
        if date_result.warning_code is not None:
            warnings.append(
                _warning_for(date_result.warning_code, dates_text, block.header_line)
            )

        normalized_title = normalize_title(title, title_lookup)
        description = "\n".join(
            strip_bullet_prefix(line) for line in block.bullet_lines
        )

        record = EmploymentRecord(
            original_title=title,
            normalized_title=normalized_title,
            company=company,
            start_date=date_result.start_date,
            end_date=date_result.end_date,
            is_current=date_result.is_current,
            date_confidence=date_result.date_confidence,
            description=description,
        )
        records.append(record)

        bullets.extend(
            extract_evidence_bullets(
                block.bullet_lines,
                "employment",
                employment_id=record.employment_id,
                phrase_map=phrase_map,
            )
        )

    return records, bullets, warnings
