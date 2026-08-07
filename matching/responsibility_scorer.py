"""Responsibility similarity scoring (SPECIFICATION.md Section 12).

Job side: confirmed responsibility texts. Candidate side: evidence
bullets from employment/project/research sections only (Section
12.1) - `CandidateProfile.evidence_bullets` already only ever
contains those three section types (Stage 4's `EmploymentSectionType`),
so every bullet passed in here is already in scope; no further
filtering is needed.
"""

from __future__ import annotations

from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from domain.schemas import (
    ComponentResult,
    EvidenceBullet,
    JobResponsibility,
    MatchEvidence,
    ScoringWarning,
)

# Section 12.4: below this, a "best match" is treated as no match at all.
MINIMUM_SIMILARITY_DEFAULT = 0.20


def build_vectorizer() -> TfidfVectorizer:
    """Section 12.3's exact configuration, unfitted. Section 14.2:
    exactly one instance is fit (on the full batch corpus - every job
    responsibility plus every candidate's evidence bullets) per
    scoring run and reused for every candidate; per-candidate fitting
    is forbidden because the IDF weights would differ candidate to
    candidate."""
    return TfidfVectorizer(
        lowercase=True,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
        norm="l2",
    )


def _apply_threshold(similarity: float, minimum_similarity: float) -> float:
    return similarity if similarity >= minimum_similarity else 0.0


def responsibility_score_from_adjusted(adjusted_values: list[float]) -> float:
    """Section 12.4's pure formula - `100 * mean(adjusted_best_i)` -
    isolated from the TF-IDF/cosine-similarity machinery so the
    Section 12.5 fixture (bests 0.76/0.65/0.58 -> 66.33) reproduces
    exactly, the same way Stage 7 isolated
    `experience_score_from_years` from calendar-date precision."""
    return round(100 * (sum(adjusted_values) / len(adjusted_values)), 2)


def calculate_responsibility_score(
    job_responsibilities: list[JobResponsibility],
    candidate_bullets: list[EvidenceBullet],
    fitted_vectorizer: Any,
    minimum_similarity: float = MINIMUM_SIMILARITY_DEFAULT,
) -> ComponentResult:
    """Section 12.4/12.5 end to end.

    - No job responsibilities -> inapplicable (`score=None`).
    - Responsibilities exist but the candidate has zero evidence
      bullets -> a real `0.0` (not `None`) + `NO_EVIDENCE_BULLETS`
      warning.
    - Every responsibility appears in `evidence` with its best bullet
      (or an explicit no-match placeholder when there are no bullets
      at all) - never dropped, and never routed through `missing`:
      `MissingItem.requirement_id` is a non-nullable UUID with no
      responsibility-shaped analog, whereas `MatchEvidence.requirement_id`
      is explicitly nullable "for responsibility matches" (Section 5).
    """
    if not job_responsibilities:
        return ComponentResult(score=None, evidence=[], missing=[], warnings=[])

    if not candidate_bullets:
        warnings = [
            ScoringWarning(
                code="NO_EVIDENCE_BULLETS",
                message=(
                    "Candidate has zero evidence bullets - no job responsibility "
                    "could be matched against anything."
                ),
                related_requirement_id=None,
            )
        ]
        evidence = [
            MatchEvidence(
                requirement_id=None,
                responsibility_id=responsibility.responsibility_id,
                matched_canonical=responsibility.original_text,
                evidence_text="No evidence bullets available for comparison.",
                evidence_section="experience",
                raw_strength=0.0,
                adjusted_strength=0.0,
            )
            for responsibility in job_responsibilities
        ]
        return ComponentResult(
            score=0.0, evidence=evidence, missing=[], warnings=warnings
        )

    responsibility_texts = [r.normalized_text for r in job_responsibilities]
    bullet_texts = [b.normalized_text for b in candidate_bullets]
    responsibility_vectors = fitted_vectorizer.transform(responsibility_texts)
    bullet_vectors = fitted_vectorizer.transform(bullet_texts)
    matrix = cosine_similarity(responsibility_vectors, bullet_vectors)

    evidence: list[MatchEvidence] = []
    adjusted_values: list[float] = []
    for i, responsibility in enumerate(job_responsibilities):
        best_index = int(matrix[i].argmax())
        best_similarity = float(matrix[i][best_index])
        best_bullet = candidate_bullets[best_index]
        adjusted = _apply_threshold(best_similarity, minimum_similarity)
        adjusted_values.append(adjusted)
        evidence.append(
            MatchEvidence(
                requirement_id=None,
                responsibility_id=responsibility.responsibility_id,
                matched_canonical=best_bullet.original_text,
                evidence_text=best_bullet.original_text,
                evidence_section=best_bullet.section_type,
                raw_strength=best_similarity,
                adjusted_strength=adjusted,
            )
        )

    score = responsibility_score_from_adjusted(adjusted_values)
    return ComponentResult(score=score, evidence=evidence, missing=[], warnings=[])
