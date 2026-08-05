"""Unit tests for resume-side certification extraction (SPECIFICATION.md
Section 9.6)."""

from __future__ import annotations

from parsing.certification_extractor import (
    build_certification_index,
    determine_held_status,
    extract_candidate_certifications,
)

CERTIFICATIONS_TAXONOMY = {
    "pmp": {
        "aliases": ["project management professional"],
        "category": "pm",
        "equivalents": {},
        "related": {},
    },
}


def _index():
    return build_certification_index(CERTIFICATIONS_TAXONOMY)


def test_certified_wording_is_held():
    records, warnings = extract_candidate_certifications(
        ["Project Management Professional (PMP), certified 2023"], _index()
    )
    assert len(records) == 1
    assert records[0].held is True
    assert records[0].pending is False
    assert warnings == []


def test_candidate_wording_is_not_held_with_warning():
    """Section 18.1 fixture: "PMP candidate" (not certified) flagged
    with warning, not held."""
    records, warnings = extract_candidate_certifications(
        ["PMP candidate, exam scheduled for 2026"], _index()
    )
    assert len(records) == 1
    assert records[0].held is False
    assert records[0].pending is True
    assert len(warnings) == 1
    assert warnings[0].code == "PENDING_CREDENTIAL"


def test_pursuing_wording_is_not_held_with_warning():
    records, warnings = extract_candidate_certifications(
        ["Pursuing PMP certification"], _index()
    )
    assert records[0].held is False
    assert records[0].pending is True
    assert warnings[0].code == "PENDING_CREDENTIAL"


def test_coursework_wording_is_not_held_without_warning():
    records, warnings = extract_candidate_certifications(
        ["PMP coursework completed"], _index()
    )
    assert records[0].held is False
    assert records[0].pending is False
    assert warnings == []


def test_issue_year_never_captured_anywhere():
    """Section 9.6: "Issue years are ignored for scoring" - there's no
    field on CertificationRecord to hold one."""
    records, _ = extract_candidate_certifications(
        ["PMP, issued 2019, certified"], _index()
    )
    assert "issue_year" not in records[0].model_dump()
    assert "2019" not in [
        v for v in records[0].model_dump().values() if isinstance(v, str)
    ]


def test_no_certification_mention_yields_no_records():
    records, warnings = extract_candidate_certifications(
        ["Nothing relevant here."], _index()
    )
    assert records == []
    assert warnings == []


def test_duplicate_mentions_deduplicated():
    records, _ = extract_candidate_certifications(
        ["PMP certified 2023", "PMP certified 2023 (Active)"], _index()
    )
    assert len(records) == 1


def test_determine_held_status_directly():
    assert determine_held_status("PMP certified") == (True, False, False)
    assert determine_held_status("PMP candidate") == (False, True, True)
    assert determine_held_status("PMP coursework") == (False, False, False)
    assert determine_held_status("PMP, issued 2023 (Active)") == (True, False, False)
