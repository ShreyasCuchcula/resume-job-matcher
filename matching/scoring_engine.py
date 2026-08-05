"""Scoring orchestration entry points (SPECIFICATION.md Section 11+).

Stage 5 wired the required/preferred qualification components on top
of matching.qualification_matcher.match_qualifications. Stage 7 adds
experience (Section 13). Responsibility similarity (Section 12) and
the final weighted MatchResult (Section 13.5/13.6) are added in a
later stage.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from domain.schemas import CandidateProfile, ComponentResult, JobProfile
from matching.experience_scorer import (
    ROLE_RELEVANCE_THRESHOLD_DEFAULT,
    calculate_experience_match,
    calculate_relevant_years,
)
from matching.qualification_matcher import match_qualifications


def score_required_qualifications(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    relevant_years: float | None = None,
) -> ComponentResult:
    """Section 10.8: "Unconfirmed jobs cannot be scored" - a hard
    assertion in the engine, defense in depth alongside the UI-level
    gate."""
    assert job.confirmed, "Unconfirmed jobs cannot be scored"
    return match_qualifications(
        job.required_qualifications, candidate, taxonomy, relevant_years=relevant_years
    )


def score_preferred_qualifications(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    relevant_years: float | None = None,
) -> ComponentResult:
    assert job.confirmed, "Unconfirmed jobs cannot be scored"
    return match_qualifications(
        job.preferred_qualifications, candidate, taxonomy, relevant_years=relevant_years
    )


def compute_relevant_years(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    run_date: date,
    vectorizer: Any = None,
    threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT,
) -> float:
    """Section 13.2/13.3's relevant-years figure, computed once and
    shared by both the experience component below and any "degree or
    equivalent experience" education requirement (Section 11.3) via
    `score_required_qualifications(..., relevant_years=...)` -
    computing it independently of whether the job states a general
    experience minimum, since an equivalent-experience clause on a
    single requirement is orthogonal to `job.minimum_relevant_years`."""
    assert job.confirmed, "Unconfirmed jobs cannot be scored"
    years, _relevant_intervals, _warnings = calculate_relevant_years(
        job,
        candidate,
        taxonomy,
        run_date=run_date,
        vectorizer=vectorizer,
        threshold=threshold,
    )
    return years


def score_experience(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    run_date: date,
    vectorizer: Any = None,
    threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT,
) -> ComponentResult:
    """Section 13.1/13.4: `score=None` when the job states no explicit
    minimum (never inferred from a seniority word alone)."""
    assert job.confirmed, "Unconfirmed jobs cannot be scored"
    return calculate_experience_match(
        job,
        candidate,
        taxonomy,
        run_date=run_date,
        vectorizer=vectorizer,
        threshold=threshold,
    )
