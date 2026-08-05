"""Unit tests for normalization/titles.py (SPECIFICATION.md Section 9.7)."""

from __future__ import annotations

from normalization.titles import build_title_lookup, normalize_title

TITLES_TAXONOMY = {
    "data analyst": {
        "aliases": ["data analyst i", "junior data analyst"],
        "related_titles": [],
    },
    "teacher": {
        "aliases": ["high school teacher", "mathematics teacher"],
        "related_titles": [],
    },
}


def test_canonical_title_normalizes_to_itself():
    lookup = build_title_lookup(TITLES_TAXONOMY)
    assert normalize_title("Data Analyst", lookup) == "data analyst"


def test_alias_normalizes_to_canonical():
    lookup = build_title_lookup(TITLES_TAXONOMY)
    assert normalize_title("Junior Data Analyst", lookup) == "data analyst"


def test_case_and_whitespace_insensitive():
    lookup = build_title_lookup(TITLES_TAXONOMY)
    assert normalize_title("  DATA   ANALYST  ", lookup) == "data analyst"


def test_unrecognized_title_returns_none():
    lookup = build_title_lookup(TITLES_TAXONOMY)
    assert normalize_title("High School Mathematics Teacher", lookup) is None


def test_unrelated_title_returns_none():
    lookup = build_title_lookup(TITLES_TAXONOMY)
    assert normalize_title("Administrative Coordinator", lookup) is None
