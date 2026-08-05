"""Experience scoring: relevant-years calculation and the experience
component formula (SPECIFICATION.md Section 13).

Duration is computed only over role-relevant employment intervals
(Section 13.2: title match against titles.json's related_titles, or
mean bullet/responsibility cosine similarity against a fitted
vectorizer), never every employment record blindly - an unrelated
job's tenure must never inflate "relevant experience" (see
sample_data/expected_rankings.md's Elliot Marsh: a reporting-analyst
role correctly contributes zero years toward a Data Scientist
posting).

The similarity path (Section 13.2 path 2) needs a fitted
TfidfVectorizer, which Section 12.3 makes a batch-level artifact fit
once per scoring run - that doesn't exist until Stage 8. `vectorizer`
is therefore optional here (default `None`): title match (path 1)
always works standalone; a caller that already has the run's fitted
vectorizer can pass it in to also exercise path 2. This mirrors Stage
5/6's `relevant_years: float | None = None` forward-compatible
parameter pattern for the same reason (Stage 7 not existing yet, at
the time).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from domain.schemas import (
    CandidateProfile,
    ComponentResult,
    EmploymentRecord,
    EvidenceBullet,
    JobProfile,
    MatchEvidence,
    ScoringWarning,
)
from normalization.titles import build_title_lookup, normalize_title

_DAYS_PER_YEAR = 365.25
ROLE_RELEVANCE_THRESHOLD_DEFAULT = 0.30


@dataclass(frozen=True)
class RelevantInterval:
    employment_id: UUID | None
    original_title: str | None
    start_date: date
    end_date: date
    date_confidence: float
    relevance_reason: str  # "title_match" | "similarity"


def merge_intervals(
    intervals: list[tuple[date, date, float]],
) -> list[tuple[date, date, float]]:
    """Section 13.3: sort by start, coalesce overlapping/touching
    intervals so parallel roles never double-count calendar time. A
    merged interval's confidence is the minimum across everything that
    fed into it (Section 13: "Use minimum confidence across
    interval")."""
    if not intervals:
        return []

    ordered = sorted(intervals, key=lambda iv: iv[0])
    merged = [ordered[0]]
    for start, end, confidence in ordered[1:]:
        last_start, last_end, last_confidence = merged[-1]
        if start <= last_end:
            merged[-1] = (
                last_start,
                max(last_end, end),
                min(last_confidence, confidence),
            )
        else:
            merged.append((start, end, confidence))
    return merged


def _effective_end(record: EmploymentRecord, run_date: date) -> date | None:
    """`end_date` is None for BOTH an ongoing ("Present") role and an
    unparseable one - `is_current` disambiguates. The scoring run's own
    `run_date` (not whatever run_date the resume happened to be parsed
    with) is what "Present" resolves to, per normalization.dates'
    documented deferral of this exact computation to this stage."""
    if record.is_current:
        return run_date
    return record.end_date


def is_title_relevant(
    normalized_title: str | None,
    target_canonical_title: str | None,
    target_related_titles: frozenset[str],
) -> bool:
    """Section 13.2 path 1, plus the self-evident case the spec's own
    "related_titles list" wording doesn't spell out but titles.json
    never lists a title as its own related title: an exact match to
    the job's own target title is trivially relevant."""
    if normalized_title is None or target_canonical_title is None:
        return False
    return (
        normalized_title == target_canonical_title
        or normalized_title in target_related_titles
    )


def is_similarity_relevant(
    role_bullet_texts: list[str],
    responsibility_texts: list[str],
    vectorizer: Any,
    threshold: float,
) -> bool:
    """Section 13.2 path 2: mean cosine similarity of a role's bullets
    against the job's responsibilities, using the run's shared fitted
    vectorizer. Unavailable (returns False) whenever there's nothing to
    compare - no vectorizer supplied yet (pre-Stage-8), no
    responsibilities, or no bullets for this role."""
    if vectorizer is None or not role_bullet_texts or not responsibility_texts:
        return False

    from sklearn.metrics.pairwise import cosine_similarity

    responsibility_vectors = vectorizer.transform(responsibility_texts)
    bullet_vectors = vectorizer.transform(role_bullet_texts)
    similarity_matrix = cosine_similarity(responsibility_vectors, bullet_vectors)
    return bool(similarity_matrix.mean() >= threshold)


def determine_role_relevance(
    record: EmploymentRecord,
    role_bullets: list[EvidenceBullet],
    job: JobProfile,
    *,
    target_canonical_title: str | None,
    target_related_titles: frozenset[str],
    vectorizer: Any = None,
    threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT,
) -> tuple[bool, str | None]:
    """Section 13.2: "a role counts if either passes." Returns
    (is_relevant, reason) - reason is None when not relevant."""
    if is_title_relevant(
        record.normalized_title, target_canonical_title, target_related_titles
    ):
        return True, "title_match"

    responsibility_texts = [r.normalized_text for r in job.responsibilities]
    bullet_texts = [b.normalized_text for b in role_bullets]
    if is_similarity_relevant(
        bullet_texts, responsibility_texts, vectorizer, threshold
    ):
        return True, "similarity"

    return False, None


def calculate_relevant_years(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    run_date: date,
    vectorizer: Any = None,
    threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT,
) -> tuple[float, list[RelevantInterval], list[ScoringWarning]]:
    """Section 13.2/13.3 end to end: determines which employment
    records are role-relevant, merges their intervals, and sums the
    result in years. Undated projects/records never contribute years
    (Section 13.3) - they're simply excluded, with a "may be
    underestimated" warning when that happens."""
    warnings: list[ScoringWarning] = []

    title_lookup = build_title_lookup(taxonomy.titles)
    target_canonical_title = (
        normalize_title(job.title, title_lookup) if job.title else None
    )
    target_related_titles = frozenset(
        taxonomy.titles.get(target_canonical_title, {}).get("related_titles", [])
        if target_canonical_title
        else []
    )

    bullets_by_employment: dict[UUID, list[EvidenceBullet]] = {}
    for bullet in candidate.evidence_bullets:
        if bullet.section_type == "employment" and bullet.employment_id is not None:
            bullets_by_employment.setdefault(bullet.employment_id, []).append(bullet)

    relevant_intervals: list[RelevantInterval] = []
    excluded_count = 0

    for record in candidate.employment:
        effective_end = _effective_end(record, run_date)
        if record.start_date is None or effective_end is None:
            excluded_count += 1
            continue

        role_bullets = bullets_by_employment.get(record.employment_id, [])
        is_relevant, reason = determine_role_relevance(
            record,
            role_bullets,
            job,
            target_canonical_title=target_canonical_title,
            target_related_titles=target_related_titles,
            vectorizer=vectorizer,
            threshold=threshold,
        )
        if not is_relevant:
            continue

        relevant_intervals.append(
            RelevantInterval(
                employment_id=record.employment_id,
                original_title=record.original_title,
                start_date=record.start_date,
                end_date=effective_end,
                date_confidence=record.date_confidence,
                relevance_reason=reason,
            )
        )

    if excluded_count:
        warnings.append(
            ScoringWarning(
                code="MISSING_DATES",
                message=(
                    f"{excluded_count} employment record(s) had missing or invalid "
                    "dates and were excluded from the relevant-experience calculation "
                    "- experience may be underestimated."
                ),
                related_requirement_id=None,
            )
        )

    if job.minimum_relevant_years is not None and not job.responsibilities:
        warnings.append(
            ScoringWarning(
                code="TITLE_ONLY_RELEVANCE",
                message=(
                    "This job has no responsibilities to compare bullets against, "
                    "so role relevance was determined by title match alone."
                ),
                related_requirement_id=None,
            )
        )

    merged = merge_intervals(
        [(iv.start_date, iv.end_date, iv.date_confidence) for iv in relevant_intervals]
    )
    total_days = sum((end - start).days for start, end, _confidence in merged)
    years_available = total_days / _DAYS_PER_YEAR

    return years_available, relevant_intervals, warnings


def experience_score_from_years(relevant_years: float, required_years: float) -> float:
    """Section 13.4's pure formula, isolated from interval math so the
    Section 18.1 fixtures (2.5/3 -> 83.33, 5/3 -> 100.00) can be
    reproduced exactly without depending on calendar-day/leap-year
    rounding: `100 * min(relevant_years / required_years, 1.0)`,
    rounded to 2dp. A `required_years` of 0 is trivially satisfied by
    any non-negative amount of experience."""
    if required_years <= 0:
        return 100.00
    return round(100 * min(relevant_years / required_years, 1.0), 2)


def calculate_experience_match(
    job: JobProfile,
    candidate: CandidateProfile,
    taxonomy: Any,
    *,
    run_date: date,
    vectorizer: Any = None,
    threshold: float = ROLE_RELEVANCE_THRESHOLD_DEFAULT,
) -> ComponentResult:
    """Section 13.1/13.4: computed only when the job states an
    explicit minimum (never inferred from a seniority word) - no
    stated minimum returns `score=None`, inapplicable. Otherwise
    `experience_score = 100 * min(relevant_years / required_years, 1.0)`,
    rounded to 2dp; zero relevant years against a real minimum is a
    genuine 0.00, not None."""
    if job.minimum_relevant_years is None:
        return ComponentResult(score=None, evidence=[], missing=[], warnings=[])

    years_available, relevant_intervals, warnings = calculate_relevant_years(
        job,
        candidate,
        taxonomy,
        run_date=run_date,
        vectorizer=vectorizer,
        threshold=threshold,
    )

    score = experience_score_from_years(years_available, job.minimum_relevant_years)

    evidence = [
        MatchEvidence(
            requirement_id=None,
            responsibility_id=None,
            matched_canonical=interval.original_title or "Relevant experience",
            evidence_text=(
                f"{interval.original_title or 'Role'}: {interval.start_date.isoformat()} "
                f"to {interval.end_date.isoformat()} ({interval.relevance_reason})."
            ),
            evidence_section="experience",
            raw_strength=interval.date_confidence,
            adjusted_strength=interval.date_confidence,
        )
        for interval in relevant_intervals
    ]

    return ComponentResult(
        score=score, evidence=evidence, missing=[], warnings=warnings
    )
