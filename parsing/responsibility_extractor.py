"""Job responsibility extraction (SPECIFICATION.md Section 10.7) and
resume evidence-bullet extraction (Section 9.2) - both are the same
underlying mechanic (split a section's lines into bullet/sentence
items, keep the original, produce a normalized copy) wrapped for their
respective domain schemas.

Bullets/sentences only ever come from the sections callers pass in -
job benefits/company boilerplate and resume contact/summary/skills/
education/certifications/interests/references text are never fed into
these functions in the first place, per Section 9.2's exclusion list.
"""

from __future__ import annotations

from uuid import UUID

from domain.enums import EmploymentSectionType
from domain.schemas import EvidenceBullet, JobResponsibility
from parsing.common import normalize_for_matching, split_into_items


def build_responsibilities_from_items(
    items: list[str], phrase_map: dict[str, str] | None = None
) -> list[JobResponsibility]:
    """Wraps already-split bullet/sentence items into JobResponsibility
    objects, preserving order and normalizing each (Section 12.2 steps
    1-3). Used directly by the no-section-headings fallback path, which
    has already sentence-segmented its text and would otherwise be
    re-segmented a second time by extract_responsibilities()."""
    return [
        JobResponsibility(
            original_text=item,
            normalized_text=normalize_for_matching(item, phrase_map),
            position=position,
        )
        for position, item in enumerate(items)
    ]


def extract_responsibilities(
    responsibility_lines: list[str], phrase_map: dict[str, str] | None = None
) -> list[JobResponsibility]:
    """Splits the responsibilities section into individual bullet/
    sentence items, preserving original text and position order, with
    a normalized copy for the TF-IDF responsibility matcher (Section
    12.2 steps 1-3: lowercase, collapse whitespace/punctuation, apply
    phrase_normalization.json - stop-word removal and n-gramming are
    the vectorizer's job at scoring time, not here)."""
    items = split_into_items(responsibility_lines)
    return build_responsibilities_from_items(items, phrase_map)


# ---------------------------------------------------------------------------
# Resume evidence bullets (Section 9.2)
# ---------------------------------------------------------------------------


def build_evidence_bullets(
    items: list[str],
    section_type: EmploymentSectionType,
    employment_id: UUID | None = None,
    phrase_map: dict[str, str] | None = None,
) -> list[EvidenceBullet]:
    """Wraps already-split bullet/sentence items into EvidenceBullet
    objects. `employment_id` links a bullet to the specific role block
    it came from (Section 9.2); it's None for project/research bullets,
    which have no employment record to attach to."""
    return [
        EvidenceBullet(
            employment_id=employment_id,
            section_type=section_type,
            original_text=item,
            normalized_text=normalize_for_matching(item, phrase_map),
        )
        for item in items
    ]


def extract_evidence_bullets(
    lines: list[str],
    section_type: EmploymentSectionType,
    employment_id: UUID | None = None,
    phrase_map: dict[str, str] | None = None,
) -> list[EvidenceBullet]:
    """Splits a block of lines (one employment role's description, or
    a whole projects/research section) into bullet/sentence items and
    wraps each as an EvidenceBullet (Section 9.2: bullet glyphs first,
    sentence-segmented prose otherwise - identical mechanics to the
    job-side responsibility extraction above)."""
    items = split_into_items(lines)
    return build_evidence_bullets(items, section_type, employment_id, phrase_map)
