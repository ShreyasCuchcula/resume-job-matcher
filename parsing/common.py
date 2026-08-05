"""Shared line/sentence/text utilities used by both job and resume
parsing (SPECIFICATION.md Section 4: `parsing/common.py`).
"""

from __future__ import annotations

import re
from functools import lru_cache

BULLET_GLYPHS = ("•", "-", "*", "–", "—")  # • - * – —
_BULLET_PREFIX_RE = re.compile(r"^[•\-*–—]\s*")
_WHITESPACE_RE = re.compile(r"\s+")

# Written numbers zero-twenty (Section 10.6: "written numbers zero-twenty converted").
NUMBER_WORDS: dict[str, int] = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def parse_number_word(token: str) -> int | None:
    """Converts a digit string or a written number word (zero-twenty)
    to an int; None if `token` is neither."""
    token = token.strip().lower()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def split_lines(text: str) -> list[str]:
    """Non-empty, stripped lines, in order."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def strip_bullet_prefix(line: str) -> str:
    """Removes a single leading bullet glyph (and following whitespace),
    if present. `"- Built dashboards"` -> `"Built dashboards"`."""
    return _BULLET_PREFIX_RE.sub("", line, count=1)


def is_bulleted(line: str) -> bool:
    stripped = line.strip()
    return any(
        stripped.startswith(glyph + " ") or stripped == glyph for glyph in BULLET_GLYPHS
    )


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@lru_cache(maxsize=1)
def _spacy_nlp():
    """Loaded lazily and cached - importing/loading spaCy's model is
    slow enough that we don't want to pay for it unless a caller
    actually needs sentence segmentation on unbulleted prose."""
    import spacy

    return spacy.load("en_core_web_sm", exclude=["ner", "lemmatizer", "tagger"])


def split_sentences(text: str) -> list[str]:
    """spaCy sentence segmentation for flowing prose (no bullet glyphs)."""
    text = collapse_whitespace(text)
    if not text:
        return []
    doc = _spacy_nlp()(text)
    return [sent.text.strip() for sent in doc.sents if sent.text.strip()]


def split_into_items(block_lines: list[str]) -> list[str]:
    """Splits a block of lines belonging to one section into individual
    bullet/sentence items (Section 9.2 / 10.7): bullet glyphs first.

    A non-bulleted line that follows a bulleted line is treated as a
    *continuation* of that bullet (a long bullet wrapped across two
    physical lines - common when text is copied from a Word doc or PDF
    - must not be split into a separate, cue-less fragment). Only
    lines that appear before any bullet, or in a block with no bullets
    at all, are treated as flowing prose and sentence-segmented.
    """
    items: list[str] = []
    current_bullet: list[str] | None = None
    prose_buffer: list[str] = []

    def flush_prose():
        if prose_buffer:
            joined = " ".join(prose_buffer)
            items.extend(split_sentences(joined))
            prose_buffer.clear()

    def flush_bullet():
        nonlocal current_bullet
        if current_bullet:
            items.append(collapse_whitespace(" ".join(current_bullet)))
        current_bullet = None

    for line in block_lines:
        if is_bulleted(line):
            flush_prose()
            flush_bullet()
            content = strip_bullet_prefix(line).strip()
            current_bullet = [content] if content else []
        elif current_bullet is not None:
            current_bullet.append(line)
        else:
            prose_buffer.append(line)

    flush_bullet()
    flush_prose()
    return items


def apply_phrase_normalization(text: str, phrase_map: dict[str, str]) -> str:
    """Applies a controlled phrase substitution map (longest phrase
    first, so multi-word entries win over single-word ones) to
    lowercase, whitespace-collapsed text (Section 12.2 step 3)."""
    result = text
    for phrase in sorted(phrase_map, key=len, reverse=True):
        replacement = phrase_map[phrase]
        pattern = re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")
        result = pattern.sub(replacement, result)
    return collapse_whitespace(result)


def normalize_for_matching(text: str, phrase_map: dict[str, str] | None = None) -> str:
    """Section 12.2 steps 1-3: lowercase, collapse whitespace, apply
    phrase normalization. (Stop-word removal and n-gramming, steps 4-5,
    are the TfidfVectorizer's job at scoring time, not parse time.)"""
    lowered = text.lower()
    lowered = re.sub(
        r"[^\w\s/+#.-]", " ", lowered
    )  # drop stray punctuation, keep word-ish chars
    lowered = collapse_whitespace(lowered)
    if phrase_map:
        lowered = apply_phrase_normalization(lowered, phrase_map)
    return lowered
