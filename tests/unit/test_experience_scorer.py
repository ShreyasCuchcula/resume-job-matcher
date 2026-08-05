"""Unit tests for matching/experience_scorer.py (SPECIFICATION.md
Section 13, Section 18.1 fixtures)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from domain.schemas import (
    CandidateProfile,
    EmploymentRecord,
    JobProfile,
    JobResponsibility,
)
from matching.experience_scorer import (
    calculate_experience_match,
    calculate_relevant_years,
    determine_role_relevance,
    experience_score_from_years,
    is_similarity_relevant,
    is_title_relevant,
    merge_intervals,
)

TAXONOMY = SimpleNamespace(
    titles={
        "data scientist": {
            "aliases": ["data scientist i"],
            "related_titles": ["senior data scientist", "applied scientist"],
        },
        "reporting analyst": {"aliases": [], "related_titles": ["data analyst"]},
    }
)


class TestMergeIntervals:
    def test_no_intervals_returns_empty(self):
        assert merge_intervals([]) == []

    def test_single_interval_passes_through(self):
        result = merge_intervals([(date(2020, 1, 1), date(2021, 1, 1), 1.0)])
        assert result == [(date(2020, 1, 1), date(2021, 1, 1), 1.0)]

    def test_overlapping_intervals_merge(self):
        """Section 13.3 fixture: [2019-01 to 2021-06] + [2020-01 to
        2022-01] -> merged [2019-01 to 2022-01]."""
        result = merge_intervals(
            [
                (date(2019, 1, 1), date(2021, 6, 1), 1.0),
                (date(2020, 1, 1), date(2022, 1, 1), 1.0),
            ]
        )
        assert result == [(date(2019, 1, 1), date(2022, 1, 1), 1.0)]

    def test_touching_intervals_merge(self):
        result = merge_intervals(
            [
                (date(2019, 1, 1), date(2020, 1, 1), 1.0),
                (date(2020, 1, 1), date(2021, 1, 1), 1.0),
            ]
        )
        assert result == [(date(2019, 1, 1), date(2021, 1, 1), 1.0)]

    def test_non_overlapping_intervals_stay_separate(self):
        result = merge_intervals(
            [
                (date(2019, 1, 1), date(2019, 6, 1), 1.0),
                (date(2021, 1, 1), date(2021, 6, 1), 1.0),
            ]
        )
        assert len(result) == 2

    def test_unsorted_input_still_merges_correctly(self):
        result = merge_intervals(
            [
                (date(2020, 1, 1), date(2022, 1, 1), 1.0),
                (date(2019, 1, 1), date(2021, 6, 1), 1.0),
            ]
        )
        assert result == [(date(2019, 1, 1), date(2022, 1, 1), 1.0)]

    def test_merged_confidence_is_minimum_across_the_group(self):
        result = merge_intervals(
            [
                (date(2019, 1, 1), date(2021, 6, 1), 1.0),
                (date(2020, 1, 1), date(2022, 1, 1), 0.6),
            ]
        )
        assert result == [(date(2019, 1, 1), date(2022, 1, 1), 0.6)]

    def test_fully_contained_interval_does_not_shrink_the_merge(self):
        result = merge_intervals(
            [
                (date(2019, 1, 1), date(2023, 1, 1), 1.0),
                (date(2020, 1, 1), date(2021, 1, 1), 1.0),
            ]
        )
        assert result == [(date(2019, 1, 1), date(2023, 1, 1), 1.0)]


class TestTitleRelevance:
    def test_exact_target_title_match_is_relevant(self):
        assert (
            is_title_relevant("data scientist", "data scientist", frozenset()) is True
        )

    def test_related_title_is_relevant(self):
        assert (
            is_title_relevant(
                "senior data scientist",
                "data scientist",
                frozenset({"senior data scientist", "applied scientist"}),
            )
            is True
        )

    def test_unrelated_title_is_not_relevant(self):
        assert (
            is_title_relevant(
                "reporting analyst",
                "data scientist",
                frozenset({"senior data scientist", "applied scientist"}),
            )
            is False
        )

    def test_none_normalized_title_is_not_relevant(self):
        assert is_title_relevant(None, "data scientist", frozenset()) is False

    def test_none_target_title_is_not_relevant(self):
        assert is_title_relevant("data scientist", None, frozenset()) is False


class TestSimilarityRelevance:
    def test_no_vectorizer_is_never_relevant(self):
        assert (
            is_similarity_relevant(["built pipelines"], ["build pipelines"], None, 0.30)
            is False
        )

    def test_no_bullets_is_never_relevant(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer().fit(["build pipelines", "query data"])
        assert (
            is_similarity_relevant([], ["build pipelines"], vectorizer, 0.30) is False
        )

    def test_no_responsibilities_is_never_relevant(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        vectorizer = TfidfVectorizer().fit(["build pipelines", "query data"])
        assert (
            is_similarity_relevant(["build pipelines"], [], vectorizer, 0.30) is False
        )

    def test_similar_bullets_pass_threshold(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        corpus = [
            "build and maintain etl pipelines",
            "query training data using sql",
            "completely unrelated retail merchandising task",
        ]
        vectorizer = TfidfVectorizer().fit(corpus)
        assert (
            is_similarity_relevant(
                ["build and maintain etl pipelines"],
                ["build and maintain etl pipelines"],
                vectorizer,
                0.30,
            )
            is True
        )

    def test_dissimilar_bullets_fail_threshold(self):
        from sklearn.feature_extraction.text import TfidfVectorizer

        corpus = [
            "build and maintain etl pipelines",
            "query training data using sql",
            "completely unrelated retail merchandising task",
        ]
        vectorizer = TfidfVectorizer().fit(corpus)
        assert (
            is_similarity_relevant(
                ["completely unrelated retail merchandising task"],
                ["build and maintain etl pipelines"],
                vectorizer,
                0.30,
            )
            is False
        )


def _employment_record(
    *,
    title: str | None,
    normalized_title: str | None,
    start_date: date | None,
    end_date: date | None,
    is_current: bool = False,
    date_confidence: float = 1.0,
):
    return EmploymentRecord(
        original_title=title,
        normalized_title=normalized_title,
        company="Some Company",
        start_date=start_date,
        end_date=end_date,
        is_current=is_current,
        date_confidence=date_confidence,
        description="",
    )


def _job(
    *,
    title: str | None,
    minimum_relevant_years: float | None,
    responsibilities: list[JobResponsibility] | None = None,
) -> JobProfile:
    return JobProfile(
        title=title,
        raw_description="x" * 150,
        minimum_relevant_years=minimum_relevant_years,
        responsibilities=responsibilities or [],
        parser_version="test",
        confirmed=True,
    )


def _candidate(employment: list[EmploymentRecord]) -> CandidateProfile:
    return CandidateProfile(
        display_identifier="Candidate 001",
        file_hash="x" * 64,
        raw_resume_text="",
        scoring_text_available=True,
        employment=employment,
        parser_version="test",
    )


class TestCalculateRelevantYears:
    def test_relevant_role_via_title_match_counts(self):
        job = _job(title="Data Scientist", minimum_relevant_years=2.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2020, 1, 1),
                    end_date=date(2023, 1, 1),
                )
            ]
        )
        years, intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert years == 3.0 or abs(years - 3.0) < 0.01
        assert len(intervals) == 1
        assert intervals[0].relevance_reason == "title_match"

    def test_irrelevant_role_via_title_mismatch_excluded(self):
        job = _job(title="Data Scientist", minimum_relevant_years=2.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Reporting Analyst",
                    normalized_title="reporting analyst",
                    start_date=date(2020, 1, 1),
                    end_date=date(2023, 1, 1),
                )
            ]
        )
        years, intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert years == 0.0
        assert intervals == []

    def test_missing_dates_excluded_and_warned(self):
        job = _job(title="Data Scientist", minimum_relevant_years=2.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=None,
                    end_date=None,
                    date_confidence=0.0,
                )
            ]
        )
        years, intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert years == 0.0
        assert any(w.code == "MISSING_DATES" for w in warnings)

    def test_current_role_uses_scoring_run_date_not_parse_time_date(self):
        job = _job(title="Data Scientist", minimum_relevant_years=2.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2024, 1, 1),
                    end_date=None,
                    is_current=True,
                )
            ]
        )
        years, intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 1, 1)
        )
        assert abs(years - 2.0) < 0.01

    def test_overlapping_relevant_roles_merge_per_section_13_3(self):
        """[2019-01 to 2021-06] + [2020-01 to 2022-01] -> ~3.0 years."""
        job = _job(title="Data Scientist", minimum_relevant_years=2.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2019, 1, 1),
                    end_date=date(2021, 6, 1),
                ),
                _employment_record(
                    title="Senior Data Scientist",
                    normalized_title="senior data scientist",
                    start_date=date(2020, 1, 1),
                    end_date=date(2022, 1, 1),
                ),
            ]
        )
        years, intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert abs(years - 3.0) < 0.01

    def test_no_responsibilities_with_a_minimum_flags_title_only_relevance(self):
        job = _job(
            title="Data Scientist", minimum_relevant_years=2.0, responsibilities=[]
        )
        candidate = _candidate([])
        _years, _intervals, warnings = calculate_relevant_years(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert any(w.code == "TITLE_ONLY_RELEVANCE" for w in warnings)


class TestExperienceScoreFormula:
    """Section 13.4: experience_score = 100 * min(relevant_years /
    required_years, 1.0). Fixtures are asserted against the pure
    formula function directly (`experience_score_from_years`) rather
    than through calendar dates, since real dates only ever produce an
    approximation of an exact `2.5` due to leap-year day counts - the
    fixture is about the formula, not calendar precision."""

    def test_fixture_2_5_of_3_is_83_33(self):
        assert experience_score_from_years(2.5, 3.0) == 83.33

    def test_fixture_5_of_3_is_100_00_never_above(self):
        assert experience_score_from_years(5.0, 3.0) == 100.00

    def test_required_years_of_zero_is_trivially_satisfied(self):
        assert experience_score_from_years(0.0, 0.0) == 100.00


class TestExperienceScoreFormulaThroughRealDates:
    """The same formula, exercised end to end through real employment
    intervals (not exact-fixture assertions - see the class above for
    those - just proving the full pipeline lands in the right
    ballpark and never exceeds 100)."""

    def test_roughly_2_5_years_against_3_required_lands_near_83(self):
        job = _job(title="Data Scientist", minimum_relevant_years=3.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2020, 1, 1),
                    end_date=date(2022, 7, 2),  # ~913 days ~= 2.5 years
                )
            ]
        )
        result = calculate_experience_match(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert 83.0 <= result.score <= 84.0

    def test_5_years_against_3_required_caps_at_100_00(self):
        job = _job(title="Data Scientist", minimum_relevant_years=3.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2015, 1, 1),
                    end_date=date(2020, 1, 1),
                )
            ]
        )
        result = calculate_experience_match(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert result.score == 100.00

    def test_no_minimum_stated_gives_none(self):
        job = _job(title="Data Scientist", minimum_relevant_years=None)
        candidate = _candidate([])
        result = calculate_experience_match(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert result.score is None
        assert result.evidence == []
        assert result.warnings == []

    def test_zero_relevant_years_is_a_real_zero_not_none(self):
        job = _job(title="Data Scientist", minimum_relevant_years=3.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Reporting Analyst",
                    normalized_title="reporting analyst",
                    start_date=date(2020, 1, 1),
                    end_date=date(2023, 1, 1),
                )
            ]
        )
        result = calculate_experience_match(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert result.score == 0.00

    def test_evidence_returned_for_each_relevant_interval(self):
        job = _job(title="Data Scientist", minimum_relevant_years=1.0)
        candidate = _candidate(
            [
                _employment_record(
                    title="Data Scientist",
                    normalized_title="data scientist",
                    start_date=date(2020, 1, 1),
                    end_date=date(2023, 1, 1),
                )
            ]
        )
        result = calculate_experience_match(
            job, candidate, TAXONOMY, run_date=date(2026, 8, 1)
        )
        assert len(result.evidence) == 1
        assert result.evidence[0].evidence_section == "experience"
        assert result.evidence[0].evidence_text.strip()


class TestDetermineRoleRelevance:
    def test_title_match_wins_without_needing_similarity(self):
        job = _job(title="Data Scientist", minimum_relevant_years=1.0)
        record = _employment_record(
            title="Data Scientist",
            normalized_title="data scientist",
            start_date=date(2020, 1, 1),
            end_date=date(2021, 1, 1),
        )
        is_relevant, reason = determine_role_relevance(
            record,
            [],
            job,
            target_canonical_title="data scientist",
            target_related_titles=frozenset(),
        )
        assert is_relevant is True
        assert reason == "title_match"

    def test_no_match_and_no_vectorizer_is_not_relevant(self):
        job = _job(title="Data Scientist", minimum_relevant_years=1.0)
        record = _employment_record(
            title="Reporting Analyst",
            normalized_title="reporting analyst",
            start_date=date(2020, 1, 1),
            end_date=date(2021, 1, 1),
        )
        is_relevant, reason = determine_role_relevance(
            record,
            [],
            job,
            target_canonical_title="data scientist",
            target_related_titles=frozenset(),
        )
        assert is_relevant is False
        assert reason is None
