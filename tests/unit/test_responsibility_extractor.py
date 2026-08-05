"""Unit tests for parsing/responsibility_extractor.py (SPECIFICATION.md
Section 10.7)."""

from __future__ import annotations

from parsing.responsibility_extractor import extract_responsibilities

PHRASE_MAP = {"built": "developed", "dashboards": "dashboard", "kpis": "kpi"}


def test_preserves_original_text_and_order():
    lines = [
        "- Built dashboards for the team.",
        "- Wrote SQL queries daily.",
        "- Tracked KPIs weekly.",
    ]
    responsibilities = extract_responsibilities(lines, PHRASE_MAP)
    assert [r.original_text for r in responsibilities] == [
        "Built dashboards for the team.",
        "Wrote SQL queries daily.",
        "Tracked KPIs weekly.",
    ]
    assert [r.position for r in responsibilities] == [0, 1, 2]


def test_normalized_text_applies_phrase_map_and_lowercases():
    lines = ["- Built dashboards for the team."]
    responsibilities = extract_responsibilities(lines, PHRASE_MAP)
    assert responsibilities[0].normalized_text == "developed dashboard for the team."


def test_no_duplicates_for_distinct_bullets():
    lines = ["- Build dashboards.", "- Write SQL queries.", "- Clean data."]
    responsibilities = extract_responsibilities(lines, PHRASE_MAP)
    assert len(responsibilities) == 3
    assert len({r.original_text for r in responsibilities}) == 3


def test_empty_section_yields_no_responsibilities():
    assert extract_responsibilities([], PHRASE_MAP) == []


def test_wrapped_bullet_across_two_lines_stays_one_responsibility():
    lines = [
        "- Build and maintain dashboards for stakeholders",
        "  across multiple business units.",
    ]
    responsibilities = extract_responsibilities(lines, PHRASE_MAP)
    assert len(responsibilities) == 1
    assert responsibilities[0].original_text == (
        "Build and maintain dashboards for stakeholders across multiple business units."
    )


def test_none_phrase_map_still_normalizes_case_and_whitespace():
    lines = ["- Built   Dashboards for the Team."]
    responsibilities = extract_responsibilities(lines, phrase_map=None)
    assert responsibilities[0].normalized_text == "built dashboards for the team."
