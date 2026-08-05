"""Unit tests for resume evidence-bullet extraction (parsing/
responsibility_extractor.py, SPECIFICATION.md Section 9.2)."""

from __future__ import annotations

from uuid import uuid4

from parsing.responsibility_extractor import (
    build_evidence_bullets,
    extract_evidence_bullets,
)

PHRASE_MAP = {"built": "developed"}


def test_extract_evidence_bullets_preserves_original_text():
    lines = ["- Built dashboards for the team.", "- Wrote SQL queries daily."]
    bullets = extract_evidence_bullets(lines, "employment")
    assert [b.original_text for b in bullets] == [
        "Built dashboards for the team.",
        "Wrote SQL queries daily.",
    ]


def test_extract_evidence_bullets_applies_phrase_normalization():
    lines = ["- Built dashboards for the team."]
    bullets = extract_evidence_bullets(lines, "employment", phrase_map=PHRASE_MAP)
    assert bullets[0].normalized_text == "developed dashboards for the team."


def test_evidence_bullet_section_type_stored():
    lines = ["- Did project work."]
    bullets = extract_evidence_bullets(lines, "project")
    assert bullets[0].section_type == "project"


def test_evidence_bullet_employment_id_linked_when_provided():
    employment_id = uuid4()
    lines = ["- Built dashboards."]
    bullets = extract_evidence_bullets(lines, "employment", employment_id=employment_id)
    assert bullets[0].employment_id == employment_id


def test_evidence_bullet_employment_id_none_for_project_and_research():
    lines = ["- Published a paper."]
    bullets = extract_evidence_bullets(lines, "research")
    assert bullets[0].employment_id is None


def test_wrapped_bullet_across_two_lines_stays_one_evidence_bullet():
    lines = [
        "- Wrote SQL queries against the retail data warehouse, including joins and window functions, to",
        "answer ad hoc business questions.",
    ]
    bullets = extract_evidence_bullets(lines, "employment")
    assert len(bullets) == 1
    assert bullets[0].original_text == (
        "Wrote SQL queries against the retail data warehouse, including joins and window "
        "functions, to answer ad hoc business questions."
    )


def test_build_evidence_bullets_from_pre_split_items():
    bullets = build_evidence_bullets(["Item one.", "Item two."], "employment")
    assert len(bullets) == 2
    assert bullets[0].original_text == "Item one."


def test_empty_section_yields_no_bullets():
    assert extract_evidence_bullets([], "employment") == []
