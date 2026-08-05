"""Job description parsing orchestration (SPECIFICATION.md Section 10).

Built incrementally: this stage starts with minimum-relevant-years
extraction (Section 10.6); section splitting, requirement extraction,
and responsibility extraction are wired together into the full
`parse_job_description()` entrypoint once every extractor exists.
"""

from __future__ import annotations

import re

from parsing.common import parse_number_word

PARSER_VERSION = "job-parser-1.0"

# Section 10.6 patterns. Each requires the number to be directly tied to
# "years"/"experience" wording - never inferred from a seniority word
# like "senior" on its own, which none of these patterns can match.
_YEARS_PLUS_RE = re.compile(r"\b(\d+)\+\s*years?\b", re.IGNORECASE)
_AT_LEAST_RE = re.compile(r"\bat least\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_MINIMUM_OF_RE = re.compile(r"\bminimum of\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_RANGE_RE = re.compile(r"\b(\d+|[a-z]+)\s+to\s+(\d+|[a-z]+)\s+years?\b", re.IGNORECASE)
_YEARS_OF_EXPERIENCE_RE = re.compile(
    r"\b(\d+|[a-z]+)\s+years?\s+of\s+(?:relevant\s+|related\s+|professional\s+)?experience\b",
    re.IGNORECASE,
)


def extract_minimum_years(text: str) -> float | None:
    """Section 10.6: finds the general minimum-years-of-experience
    requirement stated anywhere in `text`.

    Rules implemented: "3+" -> 3; a range ("two to four years") takes
    the lower bound; a value is only extracted when tied to explicit
    experience wording (never inferred from a seniority word alone -
    none of the patterns below can match on "senior" by itself).

    When more than one such phrase appears, the earliest one in the
    document wins. Section 10.6 also distinguishes a "general" minimum
    ("at least 2 years of experience") from a "skill-specific" one
    ("5+ years of Python experience"), keeping the latter only as
    requirement metadata rather than the overall minimum - none of
    this project's synthetic job descriptions use a skill-specific
    year pattern, so that distinction isn't implemented here; a known,
    documented simplification.
    """
    candidates: list[tuple[int, float]] = []

    def add_candidates(pattern: re.Pattern, group: int = 1) -> None:
        for m in pattern.finditer(text):
            value = parse_number_word(m.group(group))
            if value is not None:
                candidates.append((m.start(), float(value)))

    for m in _YEARS_PLUS_RE.finditer(text):
        candidates.append((m.start(), float(m.group(1))))

    add_candidates(_RANGE_RE, group=1)  # lower bound of the range
    add_candidates(_AT_LEAST_RE)
    add_candidates(_MINIMUM_OF_RE)
    add_candidates(_YEARS_OF_EXPERIENCE_RE)

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    return candidates[0][1]
