"""Qualification matching: skills, education, and certifications/licenses
against a job's required/preferred items (SPECIFICATION.md Section 11).

Required and preferred qualifications use identical matching mechanics
(Section 11.1) - the only difference is which JobRequirement list a
caller passes in.
"""

from __future__ import annotations

from typing import Any

from domain.schemas import (
    CandidateQualification,
    JobRequirement,
    MatchEvidence,
    MissingItem,
)

# Section 11.2: flat credit for a taxonomy-approved related skill, not
# tiered by evidence section (unlike an exact/alias match, which keeps
# the candidate's own 1.00/0.90/0.80 evidence-strength tier). Mirrors
# config/scoring.yaml's evidence_strength.related_default - hardcoded
# here the same way Stage 3/4 hardcoded their own evidence-strength
# tier constants rather than threading ScoringConfig through.
RELATED_SKILL_DEFAULT = 0.50

_NOT_IDENTIFIED_NOTE = "Not identified in the resume - this is not proof of absence."


def match_skill(
    requirement: JobRequirement,
    candidate_skills_by_canonical: dict[str, CandidateQualification],
    skills_taxonomy: dict[str, Any],
) -> tuple[float, MatchEvidence | None, MissingItem | None]:
    """Section 11.2: exact/alias match keeps the candidate's own
    evidence-strength tier; failing that, a taxonomy-approved related
    skill (looked up under the REQUIRED skill's own `related_skills`
    entry, since that's the side that declares its accepted
    substitutes) earns flat partial credit; otherwise the requirement
    is unmet."""
    exact = candidate_skills_by_canonical.get(requirement.canonical_name)
    if exact is not None:
        evidence = MatchEvidence(
            requirement_id=requirement.requirement_id,
            responsibility_id=None,
            matched_canonical=exact.canonical_name,
            evidence_text=exact.evidence_text,
            evidence_section=exact.evidence_section,
            raw_strength=exact.evidence_strength,
            adjusted_strength=exact.evidence_strength,
        )
        return exact.evidence_strength, evidence, None

    related_map = skills_taxonomy.get(requirement.canonical_name, {}).get(
        "related_skills", {}
    )
    best_match: CandidateQualification | None = None
    best_weight = 0.0
    for related_canonical, configured_weight in related_map.items():
        candidate_match = candidate_skills_by_canonical.get(related_canonical)
        if candidate_match is None:
            continue
        weight = (
            configured_weight
            if configured_weight is not None
            else RELATED_SKILL_DEFAULT
        )
        if weight > best_weight:
            best_weight = weight
            best_match = candidate_match

    if best_match is not None:
        evidence = MatchEvidence(
            requirement_id=requirement.requirement_id,
            responsibility_id=None,
            matched_canonical=best_match.canonical_name,
            evidence_text=best_match.evidence_text,
            evidence_section=best_match.evidence_section,
            raw_strength=best_match.evidence_strength,
            adjusted_strength=best_weight,
        )
        return best_weight, evidence, None

    missing = MissingItem(
        requirement_id=requirement.requirement_id,
        canonical_name=requirement.canonical_name,
        status="not_identified",
        note=_NOT_IDENTIFIED_NOTE,
    )
    return 0.0, None, missing
