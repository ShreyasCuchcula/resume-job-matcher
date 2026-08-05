"""Unit tests for parsing/certification_extractor.py (SPECIFICATION.md
Section 9.6, Section 10.4)."""

from __future__ import annotations

from parsing.certification_extractor import (
    build_certification_index,
    extract_certification_names,
)

CERTIFICATIONS_TAXONOMY = {
    "pmp": {
        "aliases": ["project management professional"],
        "category": "pm",
        "equivalents": {},
        "related": {},
    },
    "certified analytics professional": {
        "aliases": ["cap"],
        "category": "analytics",
        "equivalents": {},
        "related": {},
    },
}


def test_extract_certification_by_alias():
    index = build_certification_index(CERTIFICATIONS_TAXONOMY)
    assert extract_certification_names("PMP certification is a plus.", index) == ["pmp"]


def test_extract_certification_by_full_name():
    index = build_certification_index(CERTIFICATIONS_TAXONOMY)
    found = extract_certification_names(
        "Project Management Professional required.", index
    )
    assert found == ["pmp"]


def test_short_ambiguous_alias_requires_capitalization():
    index = build_certification_index(CERTIFICATIONS_TAXONOMY)
    # lowercase "cap" is the ordinary English word, must not match
    assert extract_certification_names("there is a cap on overtime hours", index) == []
    # capitalized "CAP" should match the certification
    assert extract_certification_names("CAP certification preferred.", index) == [
        "certified analytics professional"
    ]


def test_no_match_returns_empty_list():
    index = build_certification_index(CERTIFICATIONS_TAXONOMY)
    assert extract_certification_names("Nothing relevant here.", index) == []
