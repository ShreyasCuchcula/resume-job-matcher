"""Job title normalization via config/taxonomy/titles.json
(SPECIFICATION.md Section 9.7).
"""

from __future__ import annotations

from typing import Any


def build_title_lookup(titles_taxonomy: dict[str, Any]) -> dict[str, str]:
    """alias (lowercase) -> canonical title. Collision-freedom across
    the taxonomy is already validated at config load time
    (config/settings.py); this just flattens it for direct lookup."""
    lookup: dict[str, str] = {}
    for canonical, meta in titles_taxonomy.items():
        lookup[canonical.lower()] = canonical
        for alias in meta.get("aliases", []):
            lookup[alias.lower()] = canonical
    return lookup


def normalize_title(raw_title: str, title_lookup: dict[str, str]) -> str | None:
    """Direct alias-map lookup (Section 9.7: "titles normalized via
    titles.json"). Unlike skill/degree/certification matching, the
    input here is already an isolated title string pulled from a
    resume's role-header line - a whole-string lookup, not a free-text
    scan for an embedded phrase."""
    normalized = " ".join(raw_title.strip().lower().split())
    return title_lookup.get(normalized)
