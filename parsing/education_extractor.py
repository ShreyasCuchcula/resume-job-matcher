"""Education requirement extraction: degree level (via degrees.json),
field of study, and the "or equivalent experience" clause
(SPECIFICATION.md Section 9.5, Section 10.4, Section 11.3).

Shared by job parsing (Stage 3) and resume parsing (this stage), per
the Section 4 project structure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from domain.schemas import EducationRecord
from parsing.common import parse_number_word, split_into_items

# Section 9.5: explicit "expected"/"in progress"-type wording means the
# degree is not yet finished; an explicit "completed" (or equivalent)
# means it is. Anything else is genuinely unclear (completed=None) -
# never guessed.
_INCOMPLETE_RE = re.compile(
    r"\b(expected|anticipated|in progress|currently pursuing|pursuing)\b", re.IGNORECASE
)
_COMPLETE_RE = re.compile(r"\b(completed|conferred|graduated|awarded)\b", re.IGNORECASE)

# Bare abbreviations ("bs", "ba", "ms", "ma", "as", "aa", "be") are
# ordinary short English words/prepositions in lowercase ("as", "be").
# Requiring the matched span to be capitalized, as these are
# conventionally written ("BS", "B.S.", "MS"), avoids matching them
# inside normal prose. Aliases containing periods (e.g. "b.s.") are
# already unambiguous and don't need this guard.
_SHORT_AMBIGUOUS_MAX_LEN = 3

_WORD_BOUNDARY = r"(?<![a-zA-Z0-9])"
_WORD_BOUNDARY_END = r"(?![a-zA-Z0-9])"

_EQUIVALENT_EXPERIENCE_RE = re.compile(
    r"\bor\s+equivalent\s+experience\b", re.IGNORECASE
)
_YEARS_NEAR_RE = re.compile(
    r"\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+years?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DegreeIndexEntry:
    alias: str  # lowercase
    degree_level: str
    case_sensitive: bool
    pattern: re.Pattern


@dataclass(frozen=True)
class DegreeMatch:
    degree_level: str
    matched_text: str
    start: int
    end: int


@dataclass(frozen=True)
class FieldIndexEntry:
    phrase: str  # lowercase field name
    pattern: re.Pattern


@dataclass(frozen=True)
class EducationExtraction:
    degree_level: str | None
    field_of_study: str | None
    allows_equivalent_experience: bool
    equivalent_years: float | None
    matched_degree_pattern: bool  # True if a clean degree-phrase match was found


def build_degree_index(degrees_taxonomy: dict[str, Any]) -> list[DegreeIndexEntry]:
    entries: list[DegreeIndexEntry] = []
    for level, meta in degrees_taxonomy["levels"].items():
        for alias in meta.get("aliases", []):
            alias_lower = alias.lower()
            bare = alias_lower.replace(".", "")
            case_sensitive = (
                "." not in alias_lower
                and bare.isalpha()
                and len(bare) <= _SHORT_AMBIGUOUS_MAX_LEN
            )
            pattern = re.compile(
                _WORD_BOUNDARY + re.escape(alias_lower) + _WORD_BOUNDARY_END,
                re.IGNORECASE,
            )
            entries.append(
                DegreeIndexEntry(alias_lower, level, case_sensitive, pattern)
            )
    # Longest alias first so "bachelor's degree" wins over a hypothetical shorter overlap.
    entries.sort(key=lambda e: -len(e.alias))
    return entries


def find_degree(text: str, degree_index: list[DegreeIndexEntry]) -> DegreeMatch | None:
    """First (leftmost, longest-alias-preferred) degree-level match in
    `text`, or None."""
    best: DegreeMatch | None = None
    for entry in degree_index:
        m = entry.pattern.search(text)
        if not m:
            continue
        matched_text = text[m.start() : m.end()]
        if entry.case_sensitive and not matched_text[:1].isupper():
            continue
        if best is None or m.start() < best.start:
            best = DegreeMatch(entry.degree_level, matched_text, m.start(), m.end())
    return best


def build_field_index(fields_taxonomy: dict[str, Any]) -> list[FieldIndexEntry]:
    """One entry per known field-of-study name, longest-phrase-first so
    e.g. "computer science" is preferred over a hypothetical shorter
    overlapping name."""
    entries = [
        FieldIndexEntry(
            field.lower(),
            re.compile(
                _WORD_BOUNDARY + re.escape(field.lower()) + _WORD_BOUNDARY_END,
                re.IGNORECASE,
            ),
        )
        for field in fields_taxonomy
    ]
    entries.sort(key=lambda e: -len(e.phrase))
    return entries


def find_field_of_study(text: str, field_index: list[FieldIndexEntry]) -> str | None:
    """Finds the first (leftmost) known field-of-study name mentioned
    in `text`, via the same taxonomy-matching approach as skills and
    certifications - not a regex capture of arbitrary text after "in",
    which breaks on compound phrasing like "a quantitative field such
    as Statistics, Computer Science, or Data Science" (Section 10.4:
    "education (degree pattern + field)"). Job descriptions that list
    several comma-separated alternative fields are stored as their
    first-mentioned field only - a known, documented simplification."""
    best: tuple[int, str] | None = None
    for entry in field_index:
        m = entry.pattern.search(text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), entry.phrase)
    return best[1] if best else None


def find_equivalent_experience_clause(text: str) -> tuple[bool, float | None]:
    """Detects "...or equivalent experience..." (Section 10.4/11.3).
    Returns (allows_equivalent_experience, equivalent_years). Years are
    only ever populated when an explicit number is stated near the
    clause - never invented (Section 11.3: "If equivalent years are
    not stated in the description, do not invent them")."""
    match = _EQUIVALENT_EXPERIENCE_RE.search(text)
    if not match:
        return False, None

    window = text[match.end() : match.end() + 40]
    years_match = _YEARS_NEAR_RE.search(window)
    if not years_match:
        return True, None

    years = parse_number_word(years_match.group(1))
    return True, (float(years) if years is not None else None)


def extract_education(
    text: str, degree_index: list[DegreeIndexEntry], field_index: list[FieldIndexEntry]
) -> EducationExtraction | None:
    """Full education-requirement extraction over a classified
    sentence: degree level, field of study, and the equivalent-
    experience clause. Returns None if no degree is mentioned at all."""
    degree_match = find_degree(text, degree_index)
    if degree_match is None:
        return None

    field = find_field_of_study(text, field_index)
    allows_equivalent, equivalent_years = find_equivalent_experience_clause(text)

    return EducationExtraction(
        degree_level=degree_match.degree_level,
        field_of_study=field,
        allows_equivalent_experience=allows_equivalent,
        equivalent_years=equivalent_years,
        matched_degree_pattern=True,
    )


def determine_completion_status(text: str) -> bool | None:
    """Section 9.5: explicit incomplete wording ("expected", "in
    progress", ...) -> False; explicit completion wording ("completed",
    "conferred", ...) -> True; neither -> None (unclear), never
    guessed."""
    if _INCOMPLETE_RE.search(text):
        return False
    if _COMPLETE_RE.search(text):
        return True
    return None


def extract_candidate_education(
    education_lines: list[str],
    degree_index: list[DegreeIndexEntry],
    field_index: list[FieldIndexEntry],
) -> list[EducationRecord]:
    """Section 9.5, resume side: one EducationRecord per distinct
    degree mentioned in the education section. Deliberately has no
    graduation-year field at all (Section 9.4: dropped at extraction
    time as an age proxy) - EducationRecord's schema simply doesn't
    carry one."""
    records: list[EducationRecord] = []
    seen: set[tuple[str | None, str | None]] = set()

    for item in split_into_items(education_lines):
        extraction = extract_education(item, degree_index, field_index)
        if extraction is None:
            continue
        key = (extraction.degree_level, extraction.field_of_study)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            EducationRecord(
                degree_level=extraction.degree_level,
                field_of_study=extraction.field_of_study,
                completed=determine_completion_status(item),
                original_text=item,
            )
        )

    return records
