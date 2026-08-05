"""Qualification matching: skills, education, and certifications/licenses
against a job's required/preferred items (SPECIFICATION.md Section 11).

Required and preferred qualifications use identical matching mechanics
(Section 11.1) - the only difference is which JobRequirement list a
caller passes in.
"""

from __future__ import annotations

from typing import Any

from domain.schemas import (
    CandidateProfile,
    CandidateQualification,
    CertificationRecord,
    EducationRecord,
    JobRequirement,
    MatchEvidence,
    MissingItem,
    ScoringWarning,
)

# Section 11.2: flat credit for a taxonomy-approved related skill, not
# tiered by evidence section (unlike an exact/alias match, which keeps
# the candidate's own 1.00/0.90/0.80 evidence-strength tier). Mirrors
# config/scoring.yaml's evidence_strength.related_default - hardcoded
# here the same way Stage 3/4 hardcoded their own evidence-strength
# tier constants rather than threading ScoringConfig through.
RELATED_SKILL_DEFAULT = 0.50

# Section 11.4: flat partial credit for a taxonomy-approved related
# (non-equivalent) credential.
RELATED_CERTIFICATION_DEFAULT = 0.50

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


# ---------------------------------------------------------------------------
# Education matching (Section 11.3)
# ---------------------------------------------------------------------------


def _degree_ladder_index(ladder: list[str], level: str | None) -> int | None:
    if level is None:
        return None
    try:
        return ladder.index(level)
    except ValueError:
        return None


def _degree_level_score(
    ladder: list[str], candidate_level: str | None, required_level: str
) -> float:
    """Section 11.3: meets/exceeds required level = 1.00; one level
    below = 0.50; lower or absent = 0.00."""
    required_index = ladder.index(required_level)
    candidate_index = _degree_ladder_index(ladder, candidate_level)
    if candidate_index is None:
        return 0.0
    if candidate_index >= required_index:
        return 1.00
    if candidate_index == required_index - 1:
        return 0.50
    return 0.0


def _field_score(
    candidate_field: str | None, required_field: str, fields_taxonomy: dict[str, Any]
) -> float:
    """Section 11.3: listed (exact) or in the "related" tier = 1.00;
    "somewhat_related" tier = 0.75; otherwise 0.00."""
    if candidate_field is None:
        return 0.0
    if candidate_field == required_field:
        return 1.00
    tiers = fields_taxonomy.get(required_field, {})
    if candidate_field in tiers.get("related", []):
        return 1.00
    if candidate_field in tiers.get("somewhat_related", []):
        return 0.75
    return 0.0


def _education_record_score(
    record: EducationRecord,
    requirement: JobRequirement,
    ladder: list[str],
    fields_taxonomy: dict[str, Any],
) -> float:
    """Combines the degree-level and field axes for one candidate
    education record against one requirement: both stated -> product;
    only one stated on the requirement -> that axis alone (Section
    11.3: "Level-only requirement... use degree_level_score alone" /
    "Field-only requirement... use field_score alone")."""
    level_score = (
        _degree_level_score(ladder, record.degree_level, requirement.degree_level)
        if requirement.degree_level is not None
        else None
    )
    field_score = (
        _field_score(record.field_of_study, requirement.field_of_study, fields_taxonomy)
        if requirement.field_of_study is not None
        else None
    )

    if level_score is not None and field_score is not None:
        return level_score * field_score
    if level_score is not None:
        return level_score
    if field_score is not None:
        return field_score
    return 0.0


def match_education(
    requirement: JobRequirement,
    candidate: CandidateProfile,
    degrees_taxonomy: dict[str, Any],
    fields_taxonomy: dict[str, Any],
    relevant_years: float | None = None,
) -> tuple[float, MatchEvidence | None, MissingItem | None, list[ScoringWarning]]:
    """Section 11.3 end to end, including the "degree or equivalent
    experience" clause. `relevant_years` is optional and unset for
    Stage 5 standalone use - Stage 7's experience scorer supplies the
    real computed value once it exists."""
    warnings: list[ScoringWarning] = []
    ladder = degrees_taxonomy["ladder"]

    best_score = 0.0
    best_record: EducationRecord | None = None
    for record in candidate.education:
        score = _education_record_score(record, requirement, ladder, fields_taxonomy)
        if best_record is None or score > best_score:
            best_score = score
            best_record = record

    degree_match = best_score
    final_match = degree_match

    if requirement.allows_equivalent_experience:
        if requirement.equivalent_years is None:
            warnings.append(
                ScoringWarning(
                    code="EQUIVALENT_YEARS_NOT_STATED",
                    message=(
                        f'"{requirement.canonical_name}" allows equivalent experience, '
                        "but the job description never states how many years - the "
                        "recruiter should confirm the required years manually rather "
                        "than the system inventing a number."
                    ),
                    related_requirement_id=requirement.requirement_id,
                )
            )
        elif relevant_years is not None and requirement.equivalent_years > 0:
            equivalence_component = min(
                relevant_years / requirement.equivalent_years, 1.0
            )
            final_match = max(degree_match, equivalence_component)

    if final_match > 0.0:
        if best_record is not None and degree_match >= final_match:
            evidence_text = best_record.original_text
            evidence_section = "education"
        else:
            evidence_text = (
                f"{relevant_years:.1f} years of relevant experience credited "
                "toward the equivalent-experience clause."
            )
            evidence_section = "experience"
        evidence = MatchEvidence(
            requirement_id=requirement.requirement_id,
            responsibility_id=None,
            matched_canonical=requirement.canonical_name,
            evidence_text=evidence_text,
            evidence_section=evidence_section,
            raw_strength=degree_match,
            adjusted_strength=final_match,
        )
        return final_match, evidence, None, warnings

    missing = MissingItem(
        requirement_id=requirement.requirement_id,
        canonical_name=requirement.canonical_name,
        status="not_identified" if not candidate.education else "unclear",
        note=(
            _NOT_IDENTIFIED_NOTE
            if not candidate.education
            else (
                "Candidate education is present but does not clearly meet this "
                "requirement's level and/or field - not proof of absence."
            )
        ),
    )
    return 0.0, None, missing, warnings


# ---------------------------------------------------------------------------
# Certification / license matching (Section 11.4)
# ---------------------------------------------------------------------------


def _best_certification_by_canonical(
    certifications: list[CertificationRecord],
) -> dict[str, CertificationRecord]:
    """One record per canonical credential, preferring a held record
    over a pending one if a candidate somehow lists both (same "best
    evidence wins" spirit as skills)."""
    best: dict[str, CertificationRecord] = {}
    for record in certifications:
        existing = best.get(record.canonical_name)
        if existing is None or (not existing.held and record.held):
            best[record.canonical_name] = record
    return best


def _pending_missing_item(
    requirement: JobRequirement, record: CertificationRecord
) -> MissingItem:
    return MissingItem(
        requirement_id=requirement.requirement_id,
        canonical_name=requirement.canonical_name,
        status="pending_credential",
        note=f'"{record.canonical_name}" appears pending, not yet held - not proof of absence.',
    )


def _pending_warning(
    requirement: JobRequirement, record: CertificationRecord
) -> ScoringWarning:
    return ScoringWarning(
        code="PENDING_CREDENTIAL",
        message=f'"{record.canonical_name}" is not yet held (candidate/pending/preparing/coursework wording) - 0.00 credit.',
        related_requirement_id=requirement.requirement_id,
    )


def match_certification(
    requirement: JobRequirement,
    candidate_certifications: list[CertificationRecord],
    certifications_taxonomy: dict[str, Any],
) -> tuple[float, MatchEvidence | None, MissingItem | None, list[ScoringWarning]]:
    """Section 11.4: exact credential (or taxonomy-approved equivalent),
    held = 1.00; taxonomy-approved related (non-equivalent) credential,
    held = configured partial; pending/preparing/coursework = 0.00 +
    warning; not identified = 0.00 + recruiter-verification warning
    when the item is required. Applies identically whether
    `requirement.type` is "certification" or "license" (Section 11.4
    bundles the two)."""
    warnings: list[ScoringWarning] = []
    by_canonical = _best_certification_by_canonical(candidate_certifications)

    exact = by_canonical.get(requirement.canonical_name)
    if exact is not None:
        if exact.held:
            evidence = MatchEvidence(
                requirement_id=requirement.requirement_id,
                responsibility_id=None,
                matched_canonical=exact.canonical_name,
                evidence_text=exact.original_text,
                evidence_section="certification",
                raw_strength=1.0,
                adjusted_strength=1.0,
            )
            return 1.0, evidence, None, warnings
        warnings.append(_pending_warning(requirement, exact))
        return 0.0, None, _pending_missing_item(requirement, exact), warnings

    cert_meta = certifications_taxonomy.get(requirement.canonical_name, {})

    for equivalent_canonical in cert_meta.get("equivalents", {}):
        candidate_record = by_canonical.get(equivalent_canonical)
        if candidate_record is None:
            continue
        if candidate_record.held:
            evidence = MatchEvidence(
                requirement_id=requirement.requirement_id,
                responsibility_id=None,
                matched_canonical=candidate_record.canonical_name,
                evidence_text=candidate_record.original_text,
                evidence_section="certification",
                raw_strength=1.0,
                adjusted_strength=1.0,
            )
            return 1.0, evidence, None, warnings
        warnings.append(_pending_warning(requirement, candidate_record))
        return 0.0, None, _pending_missing_item(requirement, candidate_record), warnings

    best_related: CertificationRecord | None = None
    best_weight = 0.0
    for related_canonical, configured_weight in cert_meta.get("related", {}).items():
        candidate_record = by_canonical.get(related_canonical)
        if candidate_record is None or not candidate_record.held:
            continue
        weight = (
            configured_weight
            if configured_weight is not None
            else RELATED_CERTIFICATION_DEFAULT
        )
        if weight > best_weight:
            best_weight = weight
            best_related = candidate_record

    if best_related is not None:
        evidence = MatchEvidence(
            requirement_id=requirement.requirement_id,
            responsibility_id=None,
            matched_canonical=best_related.canonical_name,
            evidence_text=best_related.original_text,
            evidence_section="certification",
            raw_strength=1.0,
            adjusted_strength=best_weight,
        )
        return best_weight, evidence, None, warnings

    missing = MissingItem(
        requirement_id=requirement.requirement_id,
        canonical_name=requirement.canonical_name,
        status="not_identified",
        note=_NOT_IDENTIFIED_NOTE,
    )
    if requirement.required:
        warnings.append(
            ScoringWarning(
                code="MISSING_REQUIRED_CREDENTIAL",
                message=(
                    f'"{requirement.canonical_name}" was not identified in the resume. '
                    "This never auto-rejects the candidate - if this credential is "
                    "legally required for the role, verify directly with the "
                    "candidate before proceeding."
                ),
                related_requirement_id=requirement.requirement_id,
            )
        )
    return 0.0, None, missing, warnings
