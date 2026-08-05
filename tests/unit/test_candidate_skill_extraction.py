"""Unit tests for resume-side skill extraction (SPECIFICATION.md
Section 9.3, Section 18.1 fixtures)."""

from __future__ import annotations

from parsing.skill_extractor import build_skill_index, extract_candidate_skills

SKILLS_TAXONOMY = {
    "sql": {"aliases": [], "category": "database", "related_skills": {}},
    "power bi": {"aliases": ["powerbi"], "category": "bi", "related_skills": {}},
    "python": {"aliases": [], "category": "language", "related_skills": {}},
    "excel": {"aliases": [], "category": "bi", "related_skills": {}},
}


def _index():
    return build_skill_index(SKILLS_TAXONOMY)


def test_powerbi_normalizes_to_power_bi():
    """Section 18.1 fixture: "PowerBI" normalized to "power bi"."""
    quals = extract_candidate_skills(
        bullet_texts_by_section={},
        summary_text=None,
        skills_section_text="PowerBI, SQL",
        skill_index=_index(),
    )
    names = {q.canonical_name for q in quals}
    assert "power bi" in names


def test_skill_in_experience_bullet_gets_strength_1_00():
    quals = extract_candidate_skills(
        bullet_texts_by_section={"experience": ["Wrote SQL queries daily."]},
        summary_text=None,
        skills_section_text=None,
        skill_index=_index(),
    )
    sql = next(q for q in quals if q.canonical_name == "sql")
    assert sql.evidence_strength == 1.00
    assert sql.evidence_section == "experience"


def test_skill_in_project_or_research_bullet_gets_strength_1_00():
    quals = extract_candidate_skills(
        bullet_texts_by_section={"project": ["Built a SQL-based reporting tool."]},
        summary_text=None,
        skills_section_text=None,
        skill_index=_index(),
    )
    sql = next(q for q in quals if q.canonical_name == "sql")
    assert sql.evidence_strength == 1.00
    assert sql.evidence_section == "project"


def test_skill_in_summary_only_gets_strength_0_90():
    quals = extract_candidate_skills(
        bullet_texts_by_section={},
        summary_text="Analyst experienced with SQL and Python.",
        skills_section_text=None,
        skill_index=_index(),
    )
    sql = next(q for q in quals if q.canonical_name == "sql")
    assert sql.evidence_strength == 0.90
    assert sql.evidence_section == "summary"


def test_skill_in_skills_section_only_gets_strength_0_80():
    """Section 18.1 fixture: skill in skills-section-only = 0.80 confidence."""
    quals = extract_candidate_skills(
        bullet_texts_by_section={},
        summary_text=None,
        skills_section_text="SQL, Python, Power BI",
        skill_index=_index(),
    )
    sql = next(q for q in quals if q.canonical_name == "sql")
    assert sql.evidence_strength == 0.80
    assert sql.evidence_section == "skills"


def test_strongest_evidence_wins_when_skill_appears_in_multiple_sections():
    quals = extract_candidate_skills(
        bullet_texts_by_section={"experience": ["Wrote SQL queries daily."]},
        summary_text="Experienced with SQL.",
        skills_section_text="SQL, Python",
        skill_index=_index(),
    )
    sql_matches = [q for q in quals if q.canonical_name == "sql"]
    assert len(sql_matches) == 1  # recorded once
    assert sql_matches[0].evidence_strength == 1.00  # strongest evidence kept
    assert sql_matches[0].evidence_section == "experience"


def test_repetition_within_same_section_never_adds_points():
    quals = extract_candidate_skills(
        bullet_texts_by_section={
            "experience": ["Wrote SQL queries.", "More SQL work here."]
        },
        summary_text=None,
        skills_section_text=None,
        skill_index=_index(),
    )
    sql_matches = [q for q in quals if q.canonical_name == "sql"]
    assert len(sql_matches) == 1
    assert sql_matches[0].evidence_strength == 1.00


def test_skill_not_mentioned_anywhere_is_absent():
    quals = extract_candidate_skills(
        bullet_texts_by_section={},
        summary_text=None,
        skills_section_text="SQL",
        skill_index=_index(),
    )
    names = {q.canonical_name for q in quals}
    assert "python" not in names


def test_extraction_confidence_is_always_1_0():
    quals = extract_candidate_skills(
        bullet_texts_by_section={"experience": ["Used SQL and Python."]},
        summary_text=None,
        skills_section_text=None,
        skill_index=_index(),
    )
    assert all(q.extraction_confidence == 1.0 for q in quals)
