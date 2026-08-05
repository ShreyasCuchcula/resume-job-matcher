"""SQLAlchemy 2.x ORM models for all 13 tables (SPECIFICATION.md
Section 6.1). Engine-agnostic: GUID and JSON columns adapt between
SQLite (dev/test) and PostgreSQL (Section 3.3) via db/base.py.

Cascade behavior follows Section 6.2/17.2: deleting a candidate or a
job cascades through every row that exists only in service of it
(qualifications, bullets, resumes, requirements, responsibilities,
scoring runs and everything a run produced).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.base import Base, GUID, portable_json

# Column-width conventions used throughout this file:
#   Numeric(6, 3) -> fractional values in [0, 1] (confidence, strength, similarity)
#   Numeric(6, 2) -> scores in [0, 100] and years-of-experience values
_FRACTION = Numeric(6, 3, asdecimal=False)
_SCORE = Numeric(6, 2, asdecimal=False)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(GUID, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# Job side
# ---------------------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    minimum_relevant_years: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    requirements: Mapped[list["JobRequirement"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )
    responsibilities: Mapped[list["JobResponsibility"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True,
        order_by="JobResponsibility.position",
    )
    scoring_runs: Mapped[list["ScoringRun"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 3", name="ck_job_requirements_importance"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_job_requirements_confidence"),
        CheckConstraint(
            "requirement_type IN ('skill', 'education', 'certification', 'license')",
            name="ck_job_requirements_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(_FRACTION, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    allows_equivalent_experience: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    equivalent_years: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    degree_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)

    job: Mapped["Job"] = relationship(back_populates="requirements")


class JobResponsibility(Base):
    __tablename__ = "job_responsibilities"

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="responsibilities")


# ---------------------------------------------------------------------------
# Candidate side
# ---------------------------------------------------------------------------


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    display_identifier: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    employment_records: Mapped[list["EmploymentRecord"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    evidence_bullets: Mapped[list["EvidenceBullet"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )
    qualifications: Mapped[list["CandidateQualification"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: ingestion (Stage 2) persists a resume as soon as text is
    # extracted, before resume_parser.py (Stage 3) exists to produce the
    # full CandidateProfile these two columns describe. The parser fills
    # them in via an UPDATE once it runs; see migration 0002.
    parsed_json: Mapped[dict | None] = mapped_column(portable_json(), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[datetime] = _created_at()

    candidate: Mapped["Candidate"] = relationship(back_populates="resumes")


class EmploymentRecord(Base):
    __tablename__ = "employment_records"

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    normalized_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)  # display only, never scored
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date_confidence: Mapped[float] = mapped_column(_FRACTION, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="employment_records")
    evidence_bullets: Mapped[list["EvidenceBullet"]] = relationship(back_populates="employment")


class EvidenceBullet(Base):
    __tablename__ = "evidence_bullets"
    __table_args__ = (
        CheckConstraint(
            "section_type IN ('employment', 'project', 'research')",
            name="ck_evidence_bullets_section_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employment_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("employment_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    section_type: Mapped[str] = mapped_column(String(20), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="evidence_bullets")
    employment: Mapped["EmploymentRecord | None"] = relationship(back_populates="evidence_bullets")


class CandidateQualification(Base):
    __tablename__ = "candidate_qualifications"
    __table_args__ = (
        CheckConstraint(
            "qualification_type IN ('skill', 'education', 'certification', 'license')",
            name="ck_candidate_qualifications_type",
        ),
        CheckConstraint("evidence_strength BETWEEN 0 AND 1", name="ck_candidate_qualifications_strength"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_candidate_qualifications_confidence"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    qualification_type: Mapped[str] = mapped_column(String(20), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_section: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_strength: Mapped[float] = mapped_column(_FRACTION, nullable=False)
    confidence: Mapped[float] = mapped_column(_FRACTION, nullable=False)

    candidate: Mapped["Candidate"] = relationship(back_populates="qualifications")


# ---------------------------------------------------------------------------
# Scoring runs and results
# ---------------------------------------------------------------------------


class ScoringRun(Base):
    __tablename__ = "scoring_runs"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'invalidated')", name="ck_scoring_runs_status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    scoring_version: Mapped[str] = mapped_column(String(50), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(50), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(50), nullable=False)
    config_snapshot: Mapped[dict] = mapped_column(portable_json(), nullable=False)
    candidate_ids: Mapped[list] = mapped_column(portable_json(), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    job: Mapped["Job"] = relationship(back_populates="scoring_runs")
    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True
    )


class MatchResult(Base):
    __tablename__ = "match_results"
    __table_args__ = (
        UniqueConstraint("run_id", "candidate_id", name="uq_match_results_run_candidate"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("scoring_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(GUID, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    required_score: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    experience_score: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    responsibility_score: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    preferred_score: Mapped[float | None] = mapped_column(_SCORE, nullable=True)
    applied_weights: Mapped[dict] = mapped_column(portable_json(), nullable=False)
    final_score: Mapped[float] = mapped_column(_SCORE, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    run: Mapped["ScoringRun"] = relationship(back_populates="match_results")
    evidence: Mapped[list["MatchEvidence"]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan", passive_deletes=True
    )
    missing_items: Mapped[list["MissingItem"]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan", passive_deletes=True
    )
    warnings: Mapped[list["ScoringWarning"]] = relationship(
        back_populates="match_result", cascade="all, delete-orphan", passive_deletes=True
    )


class MatchEvidence(Base):
    __tablename__ = "match_evidence"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("job_requirements.id", ondelete="SET NULL"), nullable=True
    )
    responsibility_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("job_responsibilities.id", ondelete="SET NULL"), nullable=True
    )
    matched_canonical: Mapped[str] = mapped_column(String(255), nullable=False)
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_section: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_strength: Mapped[float] = mapped_column(_FRACTION, nullable=False)
    adjusted_strength: Mapped[float] = mapped_column(_FRACTION, nullable=False)

    match_result: Mapped["MatchResult"] = relationship(back_populates="evidence")


class MissingItem(Base):
    __tablename__ = "missing_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_identified', 'unclear', 'pending_credential')",
            name="ck_missing_items_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("job_requirements.id", ondelete="CASCADE"), nullable=False
    )
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)

    match_result: Mapped["MatchResult"] = relationship(back_populates="missing_items")


class ScoringWarning(Base):
    __tablename__ = "scoring_warnings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    match_result_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("match_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("job_requirements.id", ondelete="SET NULL"), nullable=True
    )

    match_result: Mapped["MatchResult"] = relationship(back_populates="warnings")
