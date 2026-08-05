"""Unit tests for matching/qualification_matcher.py (SPECIFICATION.md
Section 11, Section 18.1 fixtures)."""

from __future__ import annotations

from domain.schemas import CandidateQualification
from matching.qualification_matcher import RELATED_SKILL_DEFAULT, match_skill

SKILLS_TAXONOMY = {
    "sql": {"aliases": [], "category": "database", "related_skills": {}},
    "python": {"aliases": [], "category": "language", "related_skills": {}},
    "agile methodology": {
        "aliases": ["agile"],
        "category": "project management",
        "related_skills": {"scrum": 0.6},
    },
    "amazon sqs": {
        "aliases": [],
        "category": "cloud platform",
        "related_skills": {"message queues": 0.5},
    },
}


def _qualification(
    canonical_name: str,
    *,
    evidence_section: str = "experience",
    evidence_strength: float = 1.00,
    evidence_text: str = "Built pipelines using the tool.",
) -> CandidateQualification:
    return CandidateQualification(
        type="skill",
        canonical_name=canonical_name,
        original_text=evidence_text,
        evidence_section=evidence_section,
        evidence_text=evidence_text,
        evidence_strength=evidence_strength,
        extraction_confidence=1.0,
    )


def _requirement(canonical_name: str, *, importance: int = 3, required: bool = True):
    from domain.schemas import JobRequirement

    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text=f"Must have {canonical_name}",
        importance=importance,
        confidence=0.95,
        required=required,
    )


class TestExactSkillMatch:
    def test_bullet_evidence_keeps_strength_1_00(self):
        requirement = _requirement("sql")
        candidate_skills = {
            "sql": _qualification(
                "sql", evidence_section="experience", evidence_strength=1.00
            )
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 1.00
        assert missing is None
        assert evidence.matched_canonical == "sql"
        assert evidence.raw_strength == 1.00
        assert evidence.adjusted_strength == 1.00
        assert evidence.requirement_id == requirement.requirement_id

    def test_summary_evidence_keeps_strength_0_90(self):
        requirement = _requirement("sql")
        candidate_skills = {
            "sql": _qualification(
                "sql", evidence_section="summary", evidence_strength=0.90
            )
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 0.90
        assert evidence.evidence_section == "summary"

    def test_skills_section_only_keeps_strength_0_80(self):
        requirement = _requirement("sql")
        candidate_skills = {
            "sql": _qualification(
                "sql", evidence_section="skills", evidence_strength=0.80
            )
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 0.80
        assert evidence.evidence_section == "skills"


class TestRelatedSkillMatch:
    def test_related_skill_earns_taxonomy_configured_partial_credit(self):
        requirement = _requirement("agile methodology")
        candidate_skills = {
            "scrum": _qualification(
                "scrum", evidence_section="experience", evidence_strength=1.00
            )
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 0.6
        assert missing is None
        assert evidence.matched_canonical == "scrum"
        assert evidence.raw_strength == 1.00  # candidate's own evidence strength
        assert evidence.adjusted_strength == 0.6  # discounted related credit

    def test_related_skill_via_amazon_sqs_message_queues(self):
        requirement = _requirement("amazon sqs")
        candidate_skills = {
            "message queues": _qualification(
                "message queues", evidence_strength=0.90, evidence_section="summary"
            )
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 0.5
        assert match_value == RELATED_SKILL_DEFAULT

    def test_exact_match_takes_priority_over_related(self):
        requirement = _requirement("agile methodology")
        candidate_skills = {
            "agile methodology": _qualification(
                "agile methodology", evidence_strength=1.00
            ),
            "scrum": _qualification("scrum", evidence_strength=1.00),
        }
        match_value, evidence, missing = match_skill(
            requirement, candidate_skills, SKILLS_TAXONOMY
        )
        assert match_value == 1.00
        assert evidence.matched_canonical == "agile methodology"


class TestSkillNotFound:
    def test_skill_absent_entirely_is_zero_and_missing(self):
        requirement = _requirement("python")
        match_value, evidence, missing = match_skill(requirement, {}, SKILLS_TAXONOMY)
        assert match_value == 0.0
        assert evidence is None
        assert missing is not None
        assert missing.status == "not_identified"
        assert missing.canonical_name == "python"
        assert missing.requirement_id == requirement.requirement_id

    def test_skill_with_no_related_taxonomy_entry_at_all(self):
        requirement = _requirement("sql")
        match_value, evidence, missing = match_skill(requirement, {}, SKILLS_TAXONOMY)
        assert match_value == 0.0
        assert missing.status == "not_identified"
