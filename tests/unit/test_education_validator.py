"""Education Validator (Stage 6) test coverage: SPECIFICATION.md Section
11.3's education-matching math, exercised end to end through the public
`match_qualifications()` contract (Section 11.1) rather than the
internal `match_education()` helper directly - Stage 5 already covers
`match_education()` in isolation (`tests/unit/test_qualification_matcher.py`);
this module proves the same behavior survives the full
required/preferred scoring path, since Section 11 treats education as
a qualification item inside required/preferred rather than a separate
scoring component.

Note on the Section 18.1 "72.00" fixture required by this stage: the
only 72.00 fixture SPECIFICATION.md defines (Section 11.5) is the
all-skill preferred-qualifications worked example (Python/Power
BI/Healthcare) - there is no distinct education-only 72.00 fixture in
the spec. `TestWorkedFixture72_00` below reproduces that exact fixture
again through this stage's own test surface for traceability, and a
second test proves the identical formula machinery produces a correct,
non-fabricated score for an education-only category.
"""

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
        "python": {"aliases": [], "category": "language", "related_skills": {}},
        "power bi": {"aliases": [], "category": "bi", "related_skills": {}},
        "healthcare": {"aliases": [], "category": "domain", "related_skills": {}},
    },
    degrees={"ladder": ["high_school", "associate", "bachelor", "master", "doctorate"]},
    fields={
        "computer science": {
            "related": ["software engineering", "information technology"],
            "somewhat_related": ["mathematics", "data science"],
        },
        "data science": {
            "related": ["statistics", "computer science"],
            "somewhat_related": ["data analytics"],
        },
    },
    certifications={},
)


def _skill_qualification(canonical_name: str, evidence_strength: float, section: str):
    return CandidateQualification(
        type="skill",
        canonical_name=canonical_name,
        original_text="evidence",
        evidence_section=section,
        evidence_text="evidence",
        evidence_strength=evidence_strength,
        extraction_confidence=1.0,
    )


def _skill_requirement(canonical_name: str, importance: int, required: bool = False):
    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text=f"Requires {canonical_name}",
        importance=importance,
        confidence=0.9,
        required=required,
    )


def _education_requirement(
    *,
    degree_level: str | None,
    field_of_study: str | None,
    importance: int = 2,
    required: bool = True,
    allows_equivalent_experience: bool = False,
    equivalent_years: float | None = None,
) -> JobRequirement:
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


def _education_record(degree_level: str | None, field_of_study: str | None, text: str):
    return EducationRecord(
        degree_level=degree_level,
        field_of_study=field_of_study,
        completed=True,
        original_text=text,
    )


def _candidate(
    *,
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


class TestWorkedFixture72_00:
    """Section 11.5: Python imp 2 x 1.00 | Power BI imp 2 x 0.80 |
    Healthcare imp 1 x 0.00 -> 100 x (2 + 1.6 + 0) / 5 = 72.00. Not an
    education-specific fixture in the spec (see module docstring), but
    the same score-formula machinery this stage's education items run
    through, reproduced exactly."""

    def test_preferred_fixture_reproduces_72_00_exactly(self):
        requirements = [
            _skill_requirement("python", importance=2),
            _skill_requirement("power bi", importance=2),
            _skill_requirement("healthcare", importance=1),
        ]
        candidate = _candidate(
            skills=[
                _skill_qualification("python", 1.00, "experience"),
                _skill_qualification("power bi", 0.80, "skills"),
            ]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 72.00


class TestEducationOnlyCategoryScoring:
    """The same Section 11.1 formula applied to a category made up
    entirely of education items, proving the formula/ComponentResult
    contract is identical regardless of item type."""

    def test_single_exact_match_education_item_scores_100(self):
        requirements = [
            _education_requirement(
                degree_level="bachelor", field_of_study="computer science"
            )
        ]
        candidate = _candidate(
            education=[_education_record("bachelor", "computer science", "BS in CS.")]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 100.00
        assert len(result.evidence) == 1
        assert result.missing == []

    def test_one_level_below_and_exact_field_scores_50(self):
        requirements = [
            _education_requirement(
                degree_level="master", field_of_study="computer science"
            )
        ]
        candidate = _candidate(
            education=[_education_record("bachelor", "computer science", "BS in CS.")]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        # degree_level_score 0.50 * field_score 1.00 = 0.50 -> 100 * (imp*0.50)/imp = 50.00
        assert result.score == 50.00

    def test_somewhat_related_field_scores_75(self):
        requirements = [
            _education_requirement(
                degree_level="bachelor", field_of_study="computer science"
            )
        ]
        candidate = _candidate(
            education=[
                _education_record("bachelor", "mathematics", "BS in Mathematics.")
            ]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 75.00

    def test_level_only_requirement_ignores_field_axis(self):
        requirements = [
            _education_requirement(degree_level="bachelor", field_of_study=None)
        ]
        candidate = _candidate(
            education=[_education_record("master", "public health", "MPH.")]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 100.00

    def test_field_only_requirement_ignores_level_axis(self):
        requirements = [
            _education_requirement(degree_level=None, field_of_study="computer science")
        ]
        candidate = _candidate(
            education=[
                _education_record("high_school", "computer science", "CS coursework.")
            ]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 100.00

    def test_no_education_requirements_at_all_is_none_not_zero(self):
        """Section 11.1: empty category -> None, never 0, never free points."""
        candidate = _candidate(education=[])
        result = match_qualifications([], candidate, TAXONOMY)
        assert result.score is None
        assert result.evidence == []
        assert result.missing == []

    def test_education_required_but_candidate_has_no_records_is_zero_not_none(self):
        """Distinguish "no requirements" (inapplicable -> None) from
        "requirement exists but nothing to show for it" (a real 0.0
        contributing to a real score, plus a MissingItem)."""
        requirements = [
            _education_requirement(
                degree_level="bachelor", field_of_study="computer science"
            )
        ]
        candidate = _candidate(education=[])
        result = match_qualifications(requirements, candidate, TAXONOMY)
        assert result.score == 0.00
        assert result.missing[0].status == "not_identified"


class TestDegreeOrEquivalentContract:
    """Section 11.3's "degree or equivalent experience" clause,
    exercised through the full match_qualifications entry point (not
    just match_education directly) so the `relevant_years` kwarg's
    plumbing through the whole call chain is verified end to end -
    this is exactly the seam Stage 7's experience scorer will plug
    into."""

    def test_equivalent_years_stated_and_relevant_years_supplied_gives_full_credit(
        self,
    ):
        requirements = [
            _education_requirement(
                degree_level="master",
                field_of_study="data science",
                allows_equivalent_experience=True,
                equivalent_years=4.0,
            )
        ]
        candidate = _candidate(education=[])
        result = match_qualifications(
            requirements, candidate, TAXONOMY, relevant_years=7.0
        )
        assert result.score == 100.00
        assert result.missing == []
        assert result.warnings == []

    def test_equivalent_years_unstated_never_invents_a_number(self):
        requirements = [
            _education_requirement(
                degree_level="master",
                field_of_study="data science",
                allows_equivalent_experience=True,
                equivalent_years=None,
            )
        ]
        candidate = _candidate(education=[])
        result = match_qualifications(
            requirements, candidate, TAXONOMY, relevant_years=10.0
        )
        assert result.score == 0.00
        assert any(w.code == "EQUIVALENT_YEARS_NOT_STATED" for w in result.warnings)
        assert (
            result.warnings[0].related_requirement_id == requirements[0].requirement_id
        )

    def test_relevant_years_not_yet_wired_stage7_falls_back_to_degree_match_safely(
        self,
    ):
        """Stage 7 doesn't exist yet - callers that never pass
        relevant_years (the current real caller, matching.scoring_engine)
        must never crash and must never fabricate credit."""
        requirements = [
            _education_requirement(
                degree_level="master",
                field_of_study="data science",
                allows_equivalent_experience=True,
                equivalent_years=4.0,
            )
        ]
        candidate = _candidate(
            education=[_education_record("bachelor", "data science", "BS in DS.")]
        )
        result = match_qualifications(requirements, candidate, TAXONOMY)
        # degree_match alone: level 0.50 (one below) * field 1.00 = 0.50
        assert result.score == 50.00

    def test_equivalence_never_exceeds_1_00_even_with_far_more_years_than_required(
        self,
    ):
        requirements = [
            _education_requirement(
                degree_level="master",
                field_of_study="data science",
                allows_equivalent_experience=True,
                equivalent_years=2.0,
            )
        ]
        candidate = _candidate(education=[])
        result = match_qualifications(
            requirements, candidate, TAXONOMY, relevant_years=50.0
        )
        assert result.score == 100.00
