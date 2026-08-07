"""Scoring run orchestration (SPECIFICATION.md Section 14.2).

This is the only layer allowed to call both `matching` and `db`
(Section 2.2's dependency rule), matching `services/candidate_service.py`
and `services/job_service.py`'s precedent. Fits exactly one TF-IDF
vectorizer per batch (Section 12.3: per-candidate fitting is
forbidden), scores every candidate against the shared
`ScoringContext`, and persists the whole run - `scoring_runs` +
every candidate's `match_results` + their `match_evidence` /
`missing_items` / `scoring_warnings` - in a single transaction
(Section 6.2/14.2: the run is atomic, either all results exist or
none do).

Caller contract: `job.job_id` and every `JobRequirement.requirement_id`/
`JobResponsibility.responsibility_id` on it must already match
persisted `jobs`/`job_requirements`/`job_responsibilities` rows (i.e.
`job` is exactly what `services/job_service.parse_and_persist_job`
produced, not a freshly re-parsed copy with new random UUIDs) -
otherwise the foreign keys `match_evidence.requirement_id`/
`responsibility_id` would point at rows that don't exist. The same
applies to `candidate.candidate_id` against a persisted `candidates`
row. Reconstructing a `JobProfile`/`CandidateProfile` from already-
persisted rows (for a scoring run started fresh from the database
rather than continuing an in-memory session) is Stage 9 UI-wiring
territory, not built here.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from config.settings import AppConfig
from db.models import MatchEvidence as MatchEvidenceRow
from db.models import MatchResult as MatchResultRow
from db.models import MissingItem as MissingItemRow
from db.models import ScoringRun
from db.models import ScoringWarning as ScoringWarningRow
from domain.schemas import CandidateProfile, JobProfile, MatchResult
from matching.responsibility_scorer import build_vectorizer
from matching.scoring_engine import (
    ScoringContext,
    assert_job_is_scorable,
    score_candidate,
)


def _build_batch_corpus(
    job: JobProfile, candidates: list[CandidateProfile]
) -> list[str]:
    """Section 12.3: the vectorizer is fit on every job responsibility
    plus every bullet of every candidate in the batch - not just the
    candidate currently being scored."""
    corpus = [responsibility.normalized_text for responsibility in job.responsibilities]
    for candidate in candidates:
        corpus.extend(bullet.normalized_text for bullet in candidate.evidence_bullets)
    return corpus


def run_scoring_batch(
    session: Session,
    job: JobProfile,
    candidates: list[CandidateProfile],
    *,
    app_config: AppConfig,
    run_date: date,
) -> list[MatchResult]:
    """Section 14.2's batch algorithm end to end. Raises
    `domain.exceptions.UnscorableJobError` before touching the
    database at all if the job has no applicable scoring component
    for any candidate. On any persistence failure, the whole
    transaction rolls back - zero partial rows - and the exception
    propagates."""
    assert job.confirmed, "Unconfirmed jobs cannot be scored"
    default_weights = app_config.scoring.weights.model_dump()
    assert_job_is_scorable(job, default_weights)

    corpus = _build_batch_corpus(job, candidates)
    vectorizer = build_vectorizer().fit(corpus) if corpus else None

    context = ScoringContext(
        run_id=uuid4(),
        scoring_version=app_config.scoring.scoring_version,
        taxonomy=app_config.taxonomy,
        vectorizer=vectorizer,
        run_date=run_date,
        default_weights=default_weights,
        minimum_similarity=app_config.scoring.responsibility_matching.minimum_similarity,
        role_relevance_threshold=app_config.scoring.responsibility_matching.role_relevance_threshold,
    )

    results = [score_candidate(job, candidate, context) for candidate in candidates]

    try:
        session.add(
            ScoringRun(
                id=context.run_id,
                job_id=job.job_id,
                status="active",
                scoring_version=app_config.scoring.scoring_version,
                parser_version=job.parser_version,
                taxonomy_version=app_config.taxonomy.version,
                config_snapshot=app_config.scoring.model_dump(mode="json"),
                candidate_ids=[str(candidate.candidate_id) for candidate in candidates],
            )
        )

        for result in results:
            _persist_match_result(session, result)

        session.commit()
    except Exception:
        session.rollback()
        raise

    return results


def _persist_match_result(session: Session, result: MatchResult) -> None:
    result_row = MatchResultRow(
        run_id=result.run_id,
        job_id=result.job_id,
        candidate_id=result.candidate_id,
        required_score=result.required_score,
        experience_score=result.experience_score,
        responsibility_score=result.responsibility_score,
        preferred_score=result.preferred_score,
        applied_weights=result.applied_weights,
        final_score=result.final_score,
    )
    session.add(result_row)
    session.flush()  # assigns result_row.id for the child rows below

    for evidence in result.matched_evidence:
        session.add(
            MatchEvidenceRow(
                match_result_id=result_row.id,
                requirement_id=evidence.requirement_id,
                responsibility_id=evidence.responsibility_id,
                matched_canonical=evidence.matched_canonical,
                evidence_text=evidence.evidence_text,
                evidence_section=evidence.evidence_section,
                raw_strength=evidence.raw_strength,
                adjusted_strength=evidence.adjusted_strength,
            )
        )

    for missing in result.missing_items:
        session.add(
            MissingItemRow(
                match_result_id=result_row.id,
                requirement_id=missing.requirement_id,
                canonical_name=missing.canonical_name,
                status=missing.status,
                note=missing.note,
            )
        )

    for warning in result.warnings:
        session.add(
            ScoringWarningRow(
                match_result_id=result_row.id,
                code=warning.code,
                message=warning.message,
                related_requirement_id=warning.related_requirement_id,
            )
        )
