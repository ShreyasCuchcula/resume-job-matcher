"""Unit tests for matching/scoring_engine.py (SPECIFICATION.md Section
10.8's "unconfirmed jobs cannot be scored" hard assertion, Section 11
required/preferred dispatch)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from uuid import uuid4

from domain.exceptions import UnscorableJobError
from domain.schemas import (
    CandidateProfile,
    CandidateQualification,
    EmploymentRecord,
    EvidenceBullet,
    JobProfile,
    JobRequirement,
    JobResponsibility,
    MatchResult,
)
from matching.responsibility_scorer import build_vectorizer
from matching.scoring_engine import (
    ScoringContext,
    assert_job_is_scorable,
    compute_relevant_years,
    final_score_from_components,
    rank_match_results,
    score_candidate,
    score_experience,
    score_preferred_qualifications,
    score_required_qualifications,
)

DEFAULT_WEIGHTS = {
    "required": 0.45,
    "experience": 0.20,
    "responsibility": 0.20,
    "preferred": 0.15,
}

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


class TestFinalScoreFromComponentsFixture:
    """Section 13.6: 94.29x0.45 + 83.33x0.20 + 66.33x0.20 + 72.00x0.15
    = 83.17, exact - reproduces only with per-term rounding (see the
    function's own docstring for why round-after-sum computes 83.16)."""

    def test_fixture_reproduces_83_17_exactly(self):
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        final = final_score_from_components(scores, DEFAULT_WEIGHTS)
        assert final == 83.17

    def test_round_after_sum_alone_would_have_given_83_16(self):
        """Documents the discrepancy directly, not just in prose."""
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        raw = sum(scores[k] * DEFAULT_WEIGHTS[k] for k in DEFAULT_WEIGHTS)
        assert round(raw, 2) == 83.16


class TestAssertJobIsScorable:
    def test_job_with_nothing_at_all_raises_unscorable(self):
        job = JobProfile(
            title=None,
            raw_description="x" * 150,
            parser_version="test",
            confirmed=True,
        )
        with pytest.raises(UnscorableJobError):
            assert_job_is_scorable(job, DEFAULT_WEIGHTS)

    def test_job_with_only_responsibilities_does_not_raise(self):
        job = JobProfile(
            title=None,
            raw_description="x" * 150,
            responsibilities=[
                JobResponsibility(
                    original_text="Do X.", normalized_text="do x.", position=0
                )
            ],
            parser_version="test",
            confirmed=True,
        )
        assert_job_is_scorable(job, DEFAULT_WEIGHTS)  # must not raise

    def test_job_with_only_a_required_skill_does_not_raise(self):
        job = _job(confirmed=True)
        assert_job_is_scorable(job, DEFAULT_WEIGHTS)


class TestScoreCandidateFullIntegration:
    def _job_with_responsibility(self) -> JobProfile:
        return JobProfile(
            title="Data Scientist",
            raw_description="x" * 150,
            required_qualifications=[_requirement("sql", True)],
            preferred_qualifications=[],
            minimum_relevant_years=2.0,
            responsibilities=[
                JobResponsibility(
                    original_text="Build and maintain data pipelines.",
                    normalized_text="build and maintain data pipelines.",
                    position=0,
                )
            ],
            parser_version="test",
            confirmed=True,
        )

    def _candidate_with_evidence(self) -> CandidateProfile:
        employment_id = uuid4()
        return CandidateProfile(
            display_identifier="Candidate 001",
            file_hash="x" * 64,
            raw_resume_text="",
            scoring_text_available=True,
            skills=[
                CandidateQualification(
                    type="skill",
                    canonical_name="sql",
                    original_text="Wrote SQL queries.",
                    evidence_section="experience",
                    evidence_text="Wrote SQL queries.",
                    evidence_strength=1.0,
                    extraction_confidence=1.0,
                )
            ],
            employment=[
                EmploymentRecord(
                    employment_id=employment_id,
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
            evidence_bullets=[
                EvidenceBullet(
                    employment_id=employment_id,
                    section_type="employment",
                    original_text="Built and maintained data pipelines.",
                    normalized_text="built and maintained data pipelines.",
                )
            ],
            parser_version="test",
        )

    def _context(self) -> ScoringContext:
        vectorizer = build_vectorizer().fit(
            [
                "build and maintain data pipelines.",
                "built and maintained data pipelines.",
            ]
        )
        return ScoringContext(
            run_id=uuid4(),
            scoring_version="mvp-test",
            taxonomy=TAXONOMY,
            vectorizer=vectorizer,
            run_date=date(2026, 8, 1),
            default_weights=DEFAULT_WEIGHTS,
        )

    def test_all_four_components_present_when_applicable(self):
        job = self._job_with_responsibility()
        candidate = self._candidate_with_evidence()
        result = score_candidate(job, candidate, self._context())

        assert isinstance(result, MatchResult)
        assert result.required_score is not None
        assert result.experience_score is not None
        assert result.responsibility_score is not None
        assert result.preferred_score is None  # no preferred quals on this job
        assert "preferred" not in result.applied_weights
        assert abs(sum(result.applied_weights.values()) - 1.0) < 1e-9

    def test_final_score_is_internally_consistent_with_the_pure_formula(self):
        job = self._job_with_responsibility()
        candidate = self._candidate_with_evidence()
        result = score_candidate(job, candidate, self._context())

        scores_used = {
            key: getattr(result, f"{key}_score") for key in result.applied_weights
        }
        expected = final_score_from_components(scores_used, result.applied_weights)
        assert result.final_score == expected

    def test_evidence_and_warnings_aggregate_across_all_components(self):
        job = self._job_with_responsibility()
        candidate = self._candidate_with_evidence()
        result = score_candidate(job, candidate, self._context())

        # At least the sql skill match + the responsibility match.
        assert len(result.matched_evidence) >= 2
        sections = {e.evidence_section for e in result.matched_evidence}
        assert "experience" in sections

    def test_unconfirmed_job_raises_assertion(self):
        job = self._job_with_responsibility().model_copy(update={"confirmed": False})
        with pytest.raises(AssertionError):
            score_candidate(job, self._candidate_with_evidence(), self._context())


class TestRankMatchResults:
    def _result(
        self,
        *,
        final_score,
        required_score=50.0,
        responsibility_score=50.0,
        candidate_id=None,
    ) -> MatchResult:
        return MatchResult(
            job_id=uuid4(),
            candidate_id=candidate_id or uuid4(),
            run_id=uuid4(),
            required_score=required_score,
            experience_score=50.0,
            responsibility_score=responsibility_score,
            preferred_score=50.0,
            applied_weights=DEFAULT_WEIGHTS,
            final_score=final_score,
            scoring_version="test",
        )

    def test_higher_final_score_ranks_first(self):
        low = self._result(final_score=60.0)
        high = self._result(final_score=90.0)
        ranked = rank_match_results(
            [low, high],
            {low.candidate_id: "Candidate 002", high.candidate_id: "Candidate 001"},
        )
        assert ranked == [high, low]

    def test_ties_broken_by_required_score_descending(self):
        weak_required = self._result(final_score=80.0, required_score=60.0)
        strong_required = self._result(final_score=80.0, required_score=95.0)
        ranked = rank_match_results(
            [weak_required, strong_required],
            {
                weak_required.candidate_id: "Candidate 002",
                strong_required.candidate_id: "Candidate 001",
            },
        )
        assert ranked == [strong_required, weak_required]

    def test_ties_broken_by_responsibility_score_descending(self):
        weak = self._result(
            final_score=80.0, required_score=90.0, responsibility_score=40.0
        )
        strong = self._result(
            final_score=80.0, required_score=90.0, responsibility_score=95.0
        )
        ranked = rank_match_results(
            [weak, strong],
            {weak.candidate_id: "Candidate 002", strong.candidate_id: "Candidate 001"},
        )
        assert ranked == [strong, weak]

    def test_final_ties_broken_by_display_identifier_ascending(self):
        a = self._result(
            final_score=80.0, required_score=90.0, responsibility_score=90.0
        )
        b = self._result(
            final_score=80.0, required_score=90.0, responsibility_score=90.0
        )
        ranked = rank_match_results(
            [b, a],
            {a.candidate_id: "Candidate 001", b.candidate_id: "Candidate 002"},
        )
        assert ranked == [a, b]
