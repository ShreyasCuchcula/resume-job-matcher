"""Unit tests for parsing/skill_extractor.py (SPECIFICATION.md Section
9.3)."""

from __future__ import annotations

from parsing.skill_extractor import build_skill_index, extract_skill_names

SKILLS_TAXONOMY = {
    "sql": {
        "aliases": ["structured query language"],
        "category": "database",
        "related_skills": {},
    },
    "power bi": {
        "aliases": ["powerbi", "power-bi"],
        "category": "bi",
        "related_skills": {"tableau": 0.5},
    },
    "tableau": {"aliases": [], "category": "bi", "related_skills": {}},
    "machine learning": {"aliases": ["ml"], "category": "ml", "related_skills": {}},
    "r": {"aliases": ["r programming"], "category": "language", "related_skills": {}},
    "go": {"aliases": ["golang"], "category": "language", "related_skills": {}},
}


def test_longest_match_wins_powerbi_before_bi_substring():
    index = build_skill_index(SKILLS_TAXONOMY)
    assert extract_skill_names("Experience with PowerBI dashboards.", index) == [
        "power bi"
    ]


def test_multiword_alias_matches_regardless_of_case():
    index = build_skill_index(SKILLS_TAXONOMY)
    assert extract_skill_names("Familiar with STRUCTURED QUERY LANGUAGE.", index) == [
        "sql"
    ]


def test_machine_learning_matches_before_bare_learning_substring():
    index = build_skill_index(SKILLS_TAXONOMY)
    assert extract_skill_names("Machine learning experience required.", index) == [
        "machine learning"
    ]


def test_multiple_distinct_skills_in_one_sentence():
    index = build_skill_index(SKILLS_TAXONOMY)
    found = extract_skill_names("SQL and Power BI are both required.", index)
    assert set(found) == {"sql", "power bi"}


def test_short_ambiguous_alias_requires_capitalization():
    index = build_skill_index(SKILLS_TAXONOMY)
    assert extract_skill_names("Please go to the next section.", index) == []
    assert extract_skill_names("Go is used for backend services.", index) == ["go"]
    assert extract_skill_names("Proficient in R for statistical analysis.", index) == [
        "r"
    ]
    assert extract_skill_names("as needed for the role", index) == []


def test_no_match_returns_empty_list():
    index = build_skill_index(SKILLS_TAXONOMY)
    assert extract_skill_names("Nothing relevant mentioned here.", index) == []
