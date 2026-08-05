"""Unit tests for matching/scoring_engine.py (SPECIFICATION.md Section
10.8's "unconfirmed jobs cannot be scored" hard assertion, Section 11
required/preferred dispatch)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from domain.schemas import (
    CandidateProfile,
    EmploymentRecord,
    JobProfile,
    JobRequirement,
)
from matching.scoring_engine import (
    compute_relevant_years,
    score_experience,
    score_preferred_qualifications,
    score_required_qualifications,
)

TAXONOMY = SimpleNamespace(
    skills={"sql": {"aliases": [], "category": "database", "related_skills": {}}},
    degrees={"ladder": ["high_school", "associate", "bachelor", "master", "doctorate"]},
    fields={},
    certifications={},
    titles={
        "data scientist": {"aliases": [], "related_titles": ["senior data scientist"]}
    },
)


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        display_identifier="Candidate 001",
        file_hash="x" * 64,
        raw_resume_text="",
        scoring_text_available=True,
        parser_version="test",
    )


def _requirement(canonical_name: str, required: bool) -> JobRequirement:
    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text=f"Requires {canonical_name}",
        importance=2,
        confidence=0.9,
        required=required,
    )


def _job(*, confirmed: bool) -> JobProfile:
    return JobProfile(
        title="Data Analyst",
        raw_description="x" * 150,
        required_qualifications=[_requirement("sql", True)],
        preferred_qualifications=[],
        parser_version="test",
        confirmed=confirmed,
    )


class TestUnconfirmedJobCannotBeScored:
    def test_score_required_raises_assertion_on_unconfirmed_job(self):
        with pytest.raises(AssertionError):
            score_required_qualifications(_job(confirmed=False), _candidate(), TAXONOMY)

    def test_score_preferred_raises_assertion_on_unconfirmed_job(self):
        with pytest.raises(AssertionError):
            score_preferred_qualifications(
                _job(confirmed=False), _candidate(), TAXONOMY
            )


class TestConfirmedJobScoring:
    def test_score_required_uses_required_qualifications_list(self):
        job = _job(confirmed=True)
        result = score_required_qualifications(job, _candidate(), TAXONOMY)
        assert result.score is not None
        assert result.missing[0].canonical_name == "sql"

    def test_score_preferred_is_none_when_no_preferred_items(self):
        job = _job(confirmed=True)
        result = score_preferred_qualifications(job, _candidate(), TAXONOMY)
        assert result.score is None


def _experience_job(
    *, minimum_relevant_years: float | None, confirmed: bool = True
) -> JobProfile:
    return JobProfile(
        title="Data Scientist",
        raw_description="x" * 150,
        minimum_relevant_years=minimum_relevant_years,
        parser_version="test",
        confirmed=confirmed,
    )


def _employed_candidate() -> CandidateProfile:
    return CandidateProfile(
        display_identifier="Candidate 001",
        file_hash="x" * 64,
        raw_resume_text="",
        scoring_text_available=True,
        employment=[
            EmploymentRecord(
                original_title="Data Scientist",
                normalized_title="data scientist",
                company="Acme",
                start_date=date(2020, 1, 1),
                end_date=date(2023, 1, 1),
                is_current=False,
                date_confidence=1.0,
                description="",
            )
        ],
        parser_version="test",
    )


class TestScoreExperienceIntegration:
    def test_unconfirmed_job_raises_assertion(self):
        with pytest.raises(AssertionError):
            score_experience(
                _experience_job(minimum_relevant_years=2.0, confirmed=False),
                _employed_candidate(),
                TAXONOMY,
                run_date=date(2026, 8, 1),
            )

    def test_relevant_role_produces_a_real_score(self):
        job = _experience_job(minimum_relevant_years=2.0)
        result = score_experience(
            job, _employed_candidate(), TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert result.score == 100.00

    def test_no_minimum_gives_none(self):
        job = _experience_job(minimum_relevant_years=None)
        result = score_experience(
            job, _employed_candidate(), TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert result.score is None


class TestComputeRelevantYearsIntegration:
    def test_unconfirmed_job_raises_assertion(self):
        with pytest.raises(AssertionError):
            compute_relevant_years(
                _experience_job(minimum_relevant_years=2.0, confirmed=False),
                _employed_candidate(),
                TAXONOMY,
                run_date=date(2026, 8, 1),
            )

    def test_returns_years_available_regardless_of_stated_minimum(self):
        """Relevant years must be computable even when the job states
        no general experience minimum at all - a per-requirement
        "degree or equivalent experience" clause is orthogonal to
        job.minimum_relevant_years."""
        job = _experience_job(minimum_relevant_years=None)
        years = compute_relevant_years(
            job, _employed_candidate(), TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert abs(years - 3.0) < 0.01

    def test_feeds_directly_into_degree_or_equivalent_education_matching(self):
        """The exact seam Stage 7 was built for: relevant_years
        computed here flows straight into
        score_required_qualifications's degree-or-equivalent formula
        (Section 11.3)."""
        job = JobProfile(
            title="Data Scientist",
            raw_description="x" * 150,
            required_qualifications=[
                JobRequirement(
                    type="education",
                    canonical_name="master",
                    original_text="Master's or 2 years equivalent experience.",
                    importance=2,
                    confidence=0.9,
                    required=True,
                    degree_level="master",
                    allows_equivalent_experience=True,
                    equivalent_years=2.0,
                )
            ],
            parser_version="test",
            confirmed=True,
        )
        candidate = _employed_candidate()
        years = compute_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        result = score_required_qualifications(
            job, candidate, TAXONOMY, relevant_years=years
        )
        assert result.score == 100.00
        assert result.missing == []
