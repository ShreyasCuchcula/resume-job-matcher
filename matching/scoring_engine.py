"""Scoring orchestration entry points (SPECIFICATION.md Section 11+).

Stage 5 wired the required/preferred qualification components on top
of matching.qualification_matcher.match_qualifications. Stage 7 added
experience (Section 13.1-13.4). Stage 8 adds responsibility
similarity (Section 12), dynamic weight normalization (Section 13.5),
and the final weighted MatchResult (Section 13.6/14.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from domain.schemas import CandidateProfile, ComponentResult, JobProfile, MatchResult
from matching.experience_scorer import (
    ROLE_RELEVANCE_THRESHOLD_DEFAULT,
    calculate_experience_match,
    calculate_relevant_years,
)
from matching.qualification_matcher import match_qualifications
from matching.responsibility_scorer import (
    MINIMUM_SIMILARITY_DEFAULT,
    calculate_responsibility_score,
)
from matching.weight_normalizer import normalize_weights


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


# ---------------------------------------------------------------------------
# Stage 8: full per-candidate orchestration (Section 14.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoringContext:
    """Section 14.1: "carries fitted vectorizer, taxonomy, thresholds,
    default weights, run date (for Present), and all version strings.
    Built once per run and shared by every candidate." - in
    particular, `vectorizer` must be the SAME fitted instance for
    every candidate in a batch (Section 12.3: per-candidate fitting is
    forbidden, IDF would differ); `services/scoring_service.py` builds
    exactly one of these per run."""

    run_id: UUID
    scoring_version: str
    taxonomy: Any
    vectorizer: Any
    run_date: date
    default_weights: dict[str, float]
    minimum_similarity: float = MINIMUM_SIMILARITY_DEFAULT
    role_relevance_threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT


def assert_job_is_scorable(job: JobProfile, default_weights: dict[str, float]) -> None:
    """Section 13.5's `UnscorableJobError`, checked once per job
    rather than once per candidate: every component's applicability -
    required/preferred qualifications present, an experience minimum
    stated, responsibilities present - is determined entirely by the
    job's own fields, never by which candidate is being scored. A job
    that can never produce a score can therefore be rejected up front,
    before touching any candidate or persisting anything."""
    job_level_scores = {
        "required": 0.0 if job.required_qualifications else None,
        "preferred": 0.0 if job.preferred_qualifications else None,
        "experience": 0.0 if job.minimum_relevant_years is not None else None,
        "responsibility": 0.0 if job.responsibilities else None,
    }
    normalize_weights(job_level_scores, default_weights)


def final_score_from_components(
    scores: dict[str, float], weights: dict[str, float]
) -> float:
    """Section 13.6's formula: `sum(component_score * normalized_weight)`.

    Each component's weighted contribution is rounded to 2dp *before*
    summing, not only the final sum - the Section 13.6 worked fixture
    (94.29x0.45 + 83.33x0.20 + 66.33x0.20 + 72.00x0.15 = 83.17) only
    reproduces exactly this way; rounding once after summing computes
    83.1625 -> 83.16, one cent short of the documented fixture, despite
    the spec's own inline comment ("rounded to 2 dp") reading as a
    single final rounding step. Verified directly in Python (not just
    by hand) before choosing this over the more literal reading."""
    return round(sum(round(scores[key] * weights[key], 2) for key in weights), 2)


def score_candidate(
    job: JobProfile, candidate: CandidateProfile, context: ScoringContext
) -> MatchResult:
    """Section 14.1 end to end: builds all four components against the
    shared `ScoringContext`, normalizes weights, and computes the
    final score. `relevant_years` is computed once and threaded into
    both `required`/`preferred` (for any "degree or equivalent
    experience" requirement) and mirrors what `experience` computes
    internally - Stage 7's `calculate_experience_match` recomputes it
    rather than accepting a precomputed value, which is deterministic
    and harmless to repeat at this project's scale."""
    assert job.confirmed, "Unconfirmed jobs cannot be scored"

    relevant_years = compute_relevant_years(
        job,
        candidate,
        context.taxonomy,
        run_date=context.run_date,
        vectorizer=context.vectorizer,
        threshold=context.role_relevance_threshold,
    )
    required = score_required_qualifications(
        job, candidate, context.taxonomy, relevant_years=relevant_years
    )
    preferred = score_preferred_qualifications(
        job, candidate, context.taxonomy, relevant_years=relevant_years
    )
    experience = score_experience(
        job,
        candidate,
        context.taxonomy,
        run_date=context.run_date,
        vectorizer=context.vectorizer,
        threshold=context.role_relevance_threshold,
    )
    responsibility = calculate_responsibility_score(
        job.responsibilities,
        candidate.evidence_bullets,
        context.vectorizer,
        minimum_similarity=context.minimum_similarity,
    )

    scores = {
        "required": required.score,
        "experience": experience.score,
        "responsibility": responsibility.score,
        "preferred": preferred.score,
    }
    weights = normalize_weights(scores, context.default_weights)
    final = final_score_from_components(scores, weights)

    return MatchResult(
        job_id=job.job_id,
        candidate_id=candidate.candidate_id,
        run_id=context.run_id,
        required_score=required.score,
        experience_score=experience.score,
        responsibility_score=responsibility.score,
        preferred_score=preferred.score,
        applied_weights=weights,
        final_score=final,
        matched_evidence=(
            required.evidence
            + preferred.evidence
            + experience.evidence
            + responsibility.evidence
        ),
        missing_items=required.missing + preferred.missing,
        warnings=(
            required.warnings
            + preferred.warnings
            + experience.warnings
            + responsibility.warnings
        ),
        scoring_version=context.scoring_version,
    )


def rank_match_results(
    results: list[MatchResult], display_identifiers: dict[UUID, str]
) -> list[MatchResult]:
    """Section 13.6 tie-break order: final desc, required desc,
    responsibility desc, display_identifier asc - "no hidden criteria."
    `required_score`/`responsibility_score` can only be `None`
    uniformly across an entire run (their applicability is a property
    of the job, never of the candidate), so the `None` fallback here
    is defensive, not a case a real run can actually exercise as a
    tie-break scenario."""

    def sort_key(result: MatchResult):
        required = result.required_score if result.required_score is not None else -1.0
        responsibility = (
            result.responsibility_score
            if result.responsibility_score is not None
            else -1.0
        )
        return (
            -result.final_score,
            -required,
            -responsibility,
            display_identifiers[result.candidate_id],
        )

    return sorted(results, key=sort_key)
