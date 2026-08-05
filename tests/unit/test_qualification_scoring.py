"""Unit tests for matching/qualification_matcher.py::match_qualifications
(SPECIFICATION.md Section 11.1, Section 11.5 worked fixtures, Section
18.1)."""

from __future__ import annotations

from types import SimpleNamespace

from domain.schemas import (
    CandidateProfile,
    CandidateQualification,
    EducationRecord,
    JobRequirement,
)
from matching.qualification_matcher import match_qualifications

TAXONOMY = SimpleNamespace(
    skills={
        "sql": {"aliases": [], "category": "database", "related_skills": {}},
        "excel": {"aliases": [], "category": "office", "related_skills": {}},
        "python": {"aliases": [], "category": "language", "related_skills": {}},
        "power bi": {"aliases": [], "category": "bi", "related_skills": {}},
        "healthcare": {"aliases": [], "category": "domain", "related_skills": {}},
    },
    degrees={"ladder": ["high_school", "associate", "bachelor", "master", "doctorate"]},
    fields={
        "data analytics": {
            "related": ["business analytics"],
            "somewhat_related": ["economics"],
        }
    },
    certifications={},
)


def _skill_requirement(canonical_name: str, importance: int, required: bool = True):
    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text=f"Requires {canonical_name}",
        importance=importance,
        confidence=0.9,
        required=required,
    )


def _education_requirement(importance: int, required: bool = True):
    return JobRequirement(
        type="education",
        canonical_name="bachelor in data analytics",
        original_text="Bachelor's degree in Data Analytics or related field required.",
        importance=importance,
        confidence=0.9,
        required=required,
        degree_level="bachelor",
        field_of_study="data analytics",
    )


def _qualification(canonical_name: str, evidence_strength: float, section: str):
    return CandidateQualification(
        type="skill",
        canonical_name=canonical_name,
        original_text="evidence",
        evidence_section=section,
        evidence_text="evidence",
        evidence_strength=evidence_strength,
        extraction_confidence=1.0,
    )


class TestWorkedFixtureRequired:
    """Section 11.5: SQL imp 3 x 1.00 | Excel imp 2 x 0.80 | Related
    bachelor imp 2 x 1.00 -> 100 x (3 + 1.6 + 2) / 7 = 94.29."""

    def test_required_score_reproduces_94_29_exactly(self):
        requirements = [
            _skill_requirement("sql", importance=3),
            _skill_requirement("excel", importance=2),
            _education_requirement(importance=2),
        ]
        candidate = CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            skills=[
                _qualification("sql", 1.00, "experience"),
                _qualification("excel", 0.80, "skills"),
            ],
            education=[
                EducationRecord(
                    degree_level="bachelor",
                    field_of_study="business analytics",
                    completed=True,
                    original_text="Bachelor's in Business Analytics.",
                )
            ],
            parser_version="test",
        )

        result = match_qualifications(requirements, candidate, TAXONOMY)

        assert result.score == 94.29
        assert len(result.evidence) == 3
        assert result.missing == []


class TestWorkedFixturePreferred:
    """Section 11.5: Python imp 2 x 1.00 | Power BI imp 2 x 0.80 |
    Healthcare imp 1 x 0.00 -> 100 x (2 + 1.6 + 0) / 5 = 72.00."""

    def test_preferred_score_reproduces_72_00_exactly(self):
        requirements = [
            _skill_requirement("python", importance=2, required=False),
            _skill_requirement("power bi", importance=2, required=False),
            _skill_requirement("healthcare", importance=1, required=False),
        ]
        candidate = CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            skills=[
                _qualification("python", 1.00, "experience"),
                _qualification("power bi", 0.80, "skills"),
            ],
            parser_version="test",
        )

        result = match_qualifications(requirements, candidate, TAXONOMY)

        assert result.score == 72.00
        assert len(result.evidence) == 2
        assert len(result.missing) == 1
        assert result.missing[0].canonical_name == "healthcare"
        assert result.missing[0].status == "not_identified"


class TestEmptyCategory:
    def test_empty_requirements_list_is_none_not_zero(self):
        candidate = CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            parser_version="test",
        )
        result = match_qualifications([], candidate, TAXONOMY)
        assert result.score is None
        assert result.evidence == []
        assert result.missing == []
        assert result.warnings == []


class TestRepeatedSkillCountedOnce:
    def test_duplicate_canonical_skill_entries_contribute_only_once(self):
        requirement = _skill_requirement("sql", importance=3)
        candidate = CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            skills=[
                _qualification("sql", 1.00, "experience"),
                _qualification("sql", 0.80, "skills"),
            ],
            parser_version="test",
        )
        result = match_qualifications([requirement], candidate, TAXONOMY)
        assert len(result.evidence) == 1
        # Never double-counted: importance 3 applied exactly once, regardless
        # of which of the two same-canonical entries the dict lookup kept.
        assert result.score in (100.00, 80.00)


class TestRequirementTypeDispatch:
    def test_license_type_uses_certification_matching(self):
        requirement = JobRequirement(
            type="license",
            canonical_name="registered nurse license",
            original_text="Active RN license required.",
            importance=3,
            confidence=0.9,
            required=True,
        )
        candidate = CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            parser_version="test",
        )
        result = match_qualifications([requirement], candidate, TAXONOMY)
        assert result.score == 0.00
        assert result.missing[0].status == "not_identified"
        assert any(w.code == "MISSING_REQUIRED_CREDENTIAL" for w in result.warnings)
