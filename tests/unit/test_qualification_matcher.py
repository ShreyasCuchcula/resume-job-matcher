"""Unit tests for matching/qualification_matcher.py (SPECIFICATION.md
Section 11, Section 18.1 fixtures)."""

from __future__ import annotations

from domain.schemas import (
    CandidateProfile,
    CandidateQualification,
    EducationRecord,
    JobRequirement,
)
from matching.qualification_matcher import (
    RELATED_SKILL_DEFAULT,
    match_education,
    match_skill,
)

DEGREES_TAXONOMY = {
    "ladder": ["high_school", "associate", "bachelor", "master", "doctorate"]
}

FIELDS_TAXONOMY = {
    "computer science": {
        "related": ["software engineering", "information technology"],
        "somewhat_related": ["mathematics", "data science"],
    },
    "data science": {
        "related": ["statistics", "computer science"],
        "somewhat_related": ["data analytics"],
    },
}


def _candidate(
    education: list[EducationRecord] | None = None,
    skills: list[CandidateQualification] | None = None,
) -> CandidateProfile:
    return CandidateProfile(
        display_identifier="Candidate 001",
        file_hash="x" * 64,
        raw_resume_text="",
        scoring_text_available=True,
        education=education or [],
        skills=skills or [],
        parser_version="test",
    )


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


def _education_requirement(
    *,
    degree_level: str | None,
    field_of_study: str | None,
    importance: int = 2,
    required: bool = True,
    allows_equivalent_experience: bool = False,
    equivalent_years: float | None = None,
):
    return JobRequirement(
        type="education",
        canonical_name=degree_level or field_of_study or "education",
        original_text="Bachelor's degree required.",
        importance=importance,
        confidence=0.9,
        required=required,
        degree_level=degree_level,
        field_of_study=field_of_study,
        allows_equivalent_experience=allows_equivalent_experience,
        equivalent_years=equivalent_years,
    )


def _education_record(
    degree_level: str | None,
    field_of_study: str | None,
    text: str = "Bachelor's degree.",
) -> EducationRecord:
    return EducationRecord(
        degree_level=degree_level,
        field_of_study=field_of_study,
        completed=True,
        original_text=text,
    )


class TestEducationLevelAndField:
    def test_exact_level_and_field_scores_1_00(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "computer science")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00
        assert missing is None
        assert warnings == []

    def test_level_exceeds_required_still_scores_1_00(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("master", "computer science")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00

    def test_one_level_below_scores_0_50(self):
        requirement = _education_requirement(
            degree_level="master", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "computer science")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 0.50

    def test_two_levels_below_scores_0_00(self):
        requirement = _education_requirement(
            degree_level="doctorate", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "computer science")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 0.00
        assert missing.status == "unclear"

    def test_related_field_scores_1_00(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "software engineering")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00

    def test_somewhat_related_field_scores_0_75(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "mathematics")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 0.75

    def test_unrelated_field_scores_0_00_even_with_exact_level(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([_education_record("bachelor", "public health")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 0.00

    def test_level_only_requirement_uses_degree_level_score_alone(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study=None
        )
        candidate = _candidate([_education_record("bachelor", "public health")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00

    def test_field_only_requirement_uses_field_score_alone(self):
        requirement = _education_requirement(
            degree_level=None, field_of_study="computer science"
        )
        candidate = _candidate([_education_record("high_school", "computer science")])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00

    def test_no_education_records_is_not_identified(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate([])
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 0.00
        assert missing.status == "not_identified"

    def test_best_of_multiple_records_wins(self):
        requirement = _education_requirement(
            degree_level="bachelor", field_of_study="computer science"
        )
        candidate = _candidate(
            [
                _education_record("bachelor", "public health"),
                _education_record("bachelor", "computer science"),
            ]
        )
        match_value, evidence, missing, warnings = match_education(
            requirement, candidate, DEGREES_TAXONOMY, FIELDS_TAXONOMY
        )
        assert match_value == 1.00
        assert evidence.evidence_text == "Bachelor's degree."


class TestDegreeOrEquivalentExperience:
    def test_satisfied_through_years_when_no_degree_at_all(self):
        """Section 18.3 scenario 4 / expected_rankings.md Harper Nakamura:
        max(0.0, min(7/4, 1.0)) = 1.00."""
        requirement = _education_requirement(
            degree_level="master",
            field_of_study="data science",
            allows_equivalent_experience=True,
            equivalent_years=4.0,
        )
        candidate = _candidate([])
        match_value, evidence, missing, warnings = match_education(
            requirement,
            candidate,
            DEGREES_TAXONOMY,
            FIELDS_TAXONOMY,
            relevant_years=7.0,
        )
        assert match_value == 1.00
        assert missing is None
        assert warnings == []

    def test_equivalence_uses_max_not_sum_with_partial_degree(self):
        requirement = _education_requirement(
            degree_level="master",
            field_of_study="data science",
            allows_equivalent_experience=True,
            equivalent_years=4.0,
        )
        candidate = _candidate([_education_record("bachelor", "data science")])
        match_value, evidence, missing, warnings = match_education(
            requirement,
            candidate,
            DEGREES_TAXONOMY,
            FIELDS_TAXONOMY,
            relevant_years=1.0,
        )
        # degree_match: level 0.50 (one below) * field 1.00 = 0.50
        # equivalence: min(1/4, 1.0) = 0.25
        # max(0.50, 0.25) = 0.50
        assert match_value == 0.50

    def test_unstated_equivalent_years_never_invented_and_flags_warning(self):
        requirement = _education_requirement(
            degree_level="master",
            field_of_study="data science",
            allows_equivalent_experience=True,
            equivalent_years=None,
        )
        candidate = _candidate([])
        match_value, evidence, missing, warnings = match_education(
            requirement,
            candidate,
            DEGREES_TAXONOMY,
            FIELDS_TAXONOMY,
            relevant_years=10.0,
        )
        assert match_value == 0.00
        assert any(w.code == "EQUIVALENT_YEARS_NOT_STATED" for w in warnings)

    def test_relevant_years_not_yet_available_falls_back_to_degree_match_only(self):
        """Stage 5 standalone (Stage 7 not wired yet): relevant_years=None
        must never crash and must never fabricate credit."""
        requirement = _education_requirement(
            degree_level="master",
            field_of_study="data science",
            allows_equivalent_experience=True,
            equivalent_years=4.0,
        )
        candidate = _candidate([])
        match_value, evidence, missing, warnings = match_education(
            requirement,
            candidate,
            DEGREES_TAXONOMY,
            FIELDS_TAXONOMY,
            relevant_years=None,
        )
        assert match_value == 0.00
        assert missing is not None
