"""Scoring orchestration entry points (SPECIFICATION.md Section 11+).

Stage 5 wires the required/preferred qualification components on top
of matching.qualification_matcher.match_qualifications. Experience
(Section 13), responsibility similarity (Section 12), and the final
weighted MatchResult (Section 13.4/13.5) are added in later stages.
"""

from __future__ import annotations

from typing import Any

from domain.schemas import CandidateProfile, ComponentResult, JobProfile
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
