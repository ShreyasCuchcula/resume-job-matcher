"""Job and resume heading dictionaries and section splitting
(SPECIFICATION.md Section 9.1, Section 10.2).

Both dictionaries live here per the Section 4 project structure
(`section_detector.py # job + resume heading dictionaries`), even
though only the job side is used until the resume parser (a later
stage) needs the resume side.
"""

from __future__ import annotations

import re

from parsing.common import split_lines

# ---------------------------------------------------------------------------
# Job description headings (Section 10.2)
# ---------------------------------------------------------------------------

JOB_HEADINGS: dict[str, str] = {
    "responsibilities": "responsibilities",
    "what you will do": "responsibilities",
    "what you'll do": "responsibilities",
    "duties": "responsibilities",
    "key activities": "responsibilities",
    "the role": "responsibilities",
    "requirements": "required",
    "minimum qualifications": "required",
    "must have": "required",
    "what you need": "required",
    "preferred qualifications": "preferred",
    "nice to have": "preferred",
    "desired": "preferred",
    "bonus points": "preferred",
    "a plus": "preferred",
    "about us": "excluded",
    "company": "excluded",
    "who we are": "excluded",
    "about the team": "excluded",
    "the team": "excluded",
    "benefits": "excluded",
    "compensation": "excluded",
    "perks": "excluded",
    "eeo statement": "excluded",
    "eeo statements": "excluded",
}

# ---------------------------------------------------------------------------
# Resume headings (Section 9.1) - not used until the resume parser stage
# ---------------------------------------------------------------------------

RESUME_HEADINGS: dict[str, str] = {
    "professional experience": "experience",
    "work experience": "experience",
    "employment history": "experience",
    "experience": "experience",
    "technical skills": "skills",
    "skills": "skills",
    "core competencies": "skills",
    "tools": "skills",
    "projects": "projects",
    "academic projects": "projects",
    "personal projects": "projects",
    "research": "research",
    "research experience": "research",
    "publications": "research",
    "education": "education",
    "education and training": "education",
    "academic background": "education",
    "certifications": "certifications",
    "licenses & certifications": "certifications",
    "licenses": "certifications",
    "summary": "summary",
    "professional summary": "summary",
    "profile": "summary",
    "objective": "summary",
    "about me": "summary",
    "interests": "excluded",
    "hobbies": "excluded",
    "references": "excluded",
    "volunteering": "excluded",
}

_MAX_HEADING_LINE_LENGTH = 60
_TRAILING_PUNCTUATION_RE = re.compile(r"[:\-–—.\s]+$")


def normalize_heading_text(line: str) -> str:
    """Case-insensitive, punctuation-tolerant normalization for heading
    lookup: strips trailing colons/dashes/periods, collapses
    whitespace, lowercases."""
    stripped = _TRAILING_PUNCTUATION_RE.sub("", line.strip())
    return " ".join(stripped.lower().split())


def detect_heading(line: str, heading_map: dict[str, str]) -> str | None:
    """Returns the canonical section name if `line` is a heading-like
    line (short, no embedded sentence) whose normalized text exactly
    matches a known heading; otherwise None."""
    if len(line) > _MAX_HEADING_LINE_LENGTH:
        return None
    return heading_map.get(normalize_heading_text(line))


def split_into_sections(
    text: str, heading_map: dict[str, str]
) -> tuple[dict[str, list[str]], bool]:
    """Assigns each line to a canonical section, per Section 9.1/10.2:
    a heading line starts a new section; every following line belongs
    to that section until the next heading. Lines before the first
    heading land under the "unsectioned" key.

    Returns (section -> lines, has_any_heading) so callers can tell a
    real "no headings in this document" case (fall back to Section
    10.2's sentence-by-sentence cue classification) apart from a
    document that simply starts with unsectioned preamble text.
    """
    sections: dict[str, list[str]] = {}
    current_section = "unsectioned"
    has_any_heading = False

    for line in split_lines(text):
        heading = detect_heading(line, heading_map)
        if heading is not None:
            current_section = heading
            has_any_heading = True
            continue
        sections.setdefault(current_section, []).append(line)

    return sections, has_any_heading
