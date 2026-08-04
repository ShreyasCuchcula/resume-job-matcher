"""Pydantic v2 domain schemas (SPECIFICATION.md Section 5).

Every inter-module boundary in this project (parsing -> normalization
-> matching -> services -> db) passes these models, never bare dicts.
Field-level constraints and cross-field validators encode the schema
invariants listed at the end of Section 5:

- All component scores are `None` or in `[0, 100]`; `final_score` in `[0, 100]`.
- `applied_weights` values sum to `1.0 +/- 1e-9`.
- `importance` in {1, 2, 3}; `evidence_strength`/`confidence`/similarity-like
  fields are fractional in `[0, 1]` (exact tier values, e.g. 0.80/0.90/1.00,
  and taxonomy-configured related-skill values, e.g. 0.4/0.5/0.6, are all
  valid points in that range - the schema enforces the range, not a fixed
  discrete set, since related-skill credit is configurable per taxonomy).
- Every `MatchEvidence.evidence_text` is non-empty.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from domain.enums import (
    EmploymentSectionType,
    EvidenceSection,
    MissingItemStatus,
    RequirementType,
)

_WEIGHT_SUM_TOLERANCE = 1e-9


class _StrictModel(BaseModel):
    """Base for every domain schema: reject unknown fields so a typo'd
    key from a parser is a loud failure, not silently-dropped data."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Shared warning models
# ---------------------------------------------------------------------------


class ParsingWarning(_StrictModel):
    code: str
    message: str
    source_text: str | None = None


class ScoringWarning(_StrictModel):
    code: str
    message: str
    related_requirement_id: UUID | None = None


# ---------------------------------------------------------------------------
# Job side
# ---------------------------------------------------------------------------


class JobRequirement(_StrictModel):
    requirement_id: UUID = Field(default_factory=uuid4)
    type: RequirementType
    canonical_name: str
    original_text: str
    importance: int = Field(ge=1, le=3)
    confidence: float = Field(ge=0.0, le=1.0)
    required: bool
    allows_equivalent_experience: bool = False
    equivalent_years: float | None = Field(default=None, ge=0.0)
    degree_level: str | None = None
    field_of_study: str | None = None

    @field_validator("importance")
    @classmethod
    def _importance_must_be_1_2_or_3(cls, value: int) -> int:
        if value not in (1, 2, 3):
            raise ValueError("importance must be 1, 2, or 3")
        return value

    @model_validator(mode="after")
    def _equivalent_years_requires_flag(self) -> "JobRequirement":
        if self.equivalent_years is not None and not self.allows_equivalent_experience:
            raise ValueError("equivalent_years set without allows_equivalent_experience=True")
        return self


class JobResponsibility(_StrictModel):
    responsibility_id: UUID = Field(default_factory=uuid4)
    original_text: str
    normalized_text: str
    position: int = Field(ge=0)


class JobProfile(_StrictModel):
    job_id: UUID = Field(default_factory=uuid4)
    title: str | None
    raw_description: str
    required_qualifications: list[JobRequirement] = Field(default_factory=list)
    preferred_qualifications: list[JobRequirement] = Field(default_factory=list)
    minimum_relevant_years: float | None = Field(default=None, ge=0.0)
    responsibilities: list[JobResponsibility] = Field(default_factory=list)
    warnings: list[ParsingWarning] = Field(default_factory=list)
    parser_version: str
    confirmed: bool = False


# ---------------------------------------------------------------------------
# Candidate side
# ---------------------------------------------------------------------------


class CandidateQualification(_StrictModel):
    type: RequirementType
    canonical_name: str
    original_text: str
    evidence_section: EvidenceSection
    evidence_text: str
    evidence_strength: float = Field(ge=0.0, le=1.0)
    extraction_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_text")
    @classmethod
    def _evidence_text_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence_text must not be empty")
        return value


class EducationRecord(_StrictModel):
    degree_level: str | None
    field_of_study: str | None
    completed: bool | None  # None = unclear
    original_text: str
    # NOTE: graduation year is intentionally absent (age proxy) - Section 9.4/9.5.


class CertificationRecord(_StrictModel):
    canonical_name: str
    original_text: str
    held: bool
    pending: bool = False


class EmploymentRecord(_StrictModel):
    employment_id: UUID = Field(default_factory=uuid4)
    original_title: str | None
    normalized_title: str | None
    company: str | None  # display only, never scored
    start_date: date | None
    end_date: date | None  # None can mean "Present" (see is_current)
    is_current: bool = False
    date_confidence: float = Field(ge=0.0, le=1.0)
    description: str

    @model_validator(mode="after")
    def _end_before_start_is_invalid(self) -> "EmploymentRecord":
        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class EvidenceBullet(_StrictModel):
    bullet_id: UUID = Field(default_factory=uuid4)
    employment_id: UUID | None
    section_type: EmploymentSectionType
    original_text: str
    normalized_text: str


class CandidateProfile(_StrictModel):
    candidate_id: UUID = Field(default_factory=uuid4)
    display_identifier: str  # e.g. "Candidate 001" - deterministic (Section 14.3)
    file_hash: str
    raw_resume_text: str  # post-extraction, pre-PII-strip; stored, never scored
    scoring_text_available: bool
    skills: list[CandidateQualification] = Field(default_factory=list)
    education: list[EducationRecord] = Field(default_factory=list)
    certifications: list[CertificationRecord] = Field(default_factory=list)
    employment: list[EmploymentRecord] = Field(default_factory=list)
    evidence_bullets: list[EvidenceBullet] = Field(default_factory=list)
    warnings: list[ParsingWarning] = Field(default_factory=list)
    parser_version: str


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


class MatchEvidence(_StrictModel):
    requirement_id: UUID | None  # None for responsibility matches
    responsibility_id: UUID | None
    matched_canonical: str
    evidence_text: str
    evidence_section: str
    raw_strength: float = Field(ge=0.0, le=1.0)
    adjusted_strength: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_text")
    @classmethod
    def _evidence_text_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence_text must not be empty")
        return value


class MissingItem(_StrictModel):
    requirement_id: UUID
    canonical_name: str
    status: MissingItemStatus
    note: str  # e.g. "Not identified in the resume - this is not proof of absence."


class ComponentResult(_StrictModel):
    score: float | None = Field(default=None, ge=0.0, le=100.0)  # None = inapplicable, NOT zero
    evidence: list[MatchEvidence] = Field(default_factory=list)
    missing: list[MissingItem] = Field(default_factory=list)
    warnings: list[ScoringWarning] = Field(default_factory=list)


class MatchResult(_StrictModel):
    job_id: UUID
    candidate_id: UUID
    run_id: UUID
    required_score: float | None = Field(default=None, ge=0.0, le=100.0)
    experience_score: float | None = Field(default=None, ge=0.0, le=100.0)
    responsibility_score: float | None = Field(default=None, ge=0.0, le=100.0)
    preferred_score: float | None = Field(default=None, ge=0.0, le=100.0)
    applied_weights: dict[str, float]  # sums to 1.0 over applicable components
    final_score: float = Field(ge=0.0, le=100.0)
    matched_evidence: list[MatchEvidence] = Field(default_factory=list)
    missing_items: list[MissingItem] = Field(default_factory=list)
    warnings: list[ScoringWarning] = Field(default_factory=list)
    scoring_version: str

    @field_validator("final_score")
    @classmethod
    def _round_final_score(cls, value: float) -> float:
        return round(value, 2)

    @model_validator(mode="after")
    def _applied_weights_sum_to_one(self) -> "MatchResult":
        if not self.applied_weights:
            raise ValueError("applied_weights must not be empty")
        total = sum(self.applied_weights.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"applied_weights must sum to 1.0 (+/- 1e-9), got {total}")
        return self
