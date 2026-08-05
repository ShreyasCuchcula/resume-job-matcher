"""Unit tests for parsing/common.py."""

from __future__ import annotations

from parsing.common import (
    apply_phrase_normalization,
    collapse_whitespace,
    is_bulleted,
    normalize_for_matching,
    split_into_items,
    split_lines,
    split_sentences,
    strip_bullet_prefix,
)


def test_split_lines_drops_blank_lines():
    text = "Line one\n\n  \nLine two\n"
    assert split_lines(text) == ["Line one", "Line two"]


def test_is_bulleted_recognizes_all_glyphs():
    assert is_bulleted("- item")
    assert is_bulleted("• item")
    assert is_bulleted("* item")
    assert is_bulleted("– item")
    assert not is_bulleted("Not a bullet")


def test_strip_bullet_prefix():
    assert strip_bullet_prefix("- Built dashboards.") == "Built dashboards."
    assert strip_bullet_prefix("• Wrote SQL queries.") == "Wrote SQL queries."
    assert strip_bullet_prefix("No bullet here.") == "No bullet here."


def test_collapse_whitespace():
    assert collapse_whitespace("a   b\n\tc") == "a b c"


def test_split_into_items_bulleted_block():
    lines = ["- Built dashboards.", "- Wrote SQL queries.", "- Cleaned data."]
    assert split_into_items(lines) == [
        "Built dashboards.",
        "Wrote SQL queries.",
        "Cleaned data.",
    ]


def test_split_into_items_prose_block_uses_sentence_segmentation():
    lines = ["Built dashboards for the team. Wrote SQL queries daily."]
    items = split_into_items(lines)
    assert items == ["Built dashboards for the team.", "Wrote SQL queries daily."]


def test_apply_phrase_normalization_longest_match_first():
    phrase_map = {"key performance indicators": "kpi", "kpis": "kpi"}
    assert apply_phrase_normalization("key performance indicators", phrase_map) == "kpi"
    assert (
        apply_phrase_normalization("track kpis weekly", phrase_map)
        == "track kpi weekly"
    )


def test_normalize_for_matching_lowercases_and_normalizes():
    phrase_map = {"built": "developed"}
    result = normalize_for_matching("Built  Dashboards!", phrase_map)
    assert result == "developed dashboards"


def test_split_sentences_basic():
    sentences = split_sentences(
        "Build dashboards for stakeholders. Write SQL queries daily."
    )
    assert sentences == [
        "Build dashboards for stakeholders.",
        "Write SQL queries daily.",
    ]
