"""Job responsibility extraction (SPECIFICATION.md Section 10.7).

Bullets/sentences from the responsibilities section only - benefits
and company boilerplate never reach this function, since they live in
an "excluded" section and job_parser.py never passes that section's
lines here.
"""

from __future__ import annotations

from domain.schemas import JobResponsibility
from parsing.common import normalize_for_matching, split_into_items


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
    return [
        JobResponsibility(
            original_text=item,
            normalized_text=normalize_for_matching(item, phrase_map),
            position=position,
        )
        for position, item in enumerate(items)
    ]
