"""Job persistence orchestration (SPECIFICATION.md Section 4's
documented file layout: "create/parse/confirm/invalidate" - not built
until now, since no earlier stage needed job-level DB persistence;
Stages 0-7 worked on parsing.job_parser's pydantic JobProfile objects
directly, never touching `db`).

Post-Stage-7 addendum (pre-Stage-9 infrastructure, not part of the
original 10-stage plan - SPECIFICATION.md Section 6.3): every new job
now belongs to a Company. This is the only layer allowed to call both
`parsing` and `db` (Section 2.2's dependency rule), matching
`services/candidate_service.py`'s precedent.

Scope note: `invalidate` (Section 6.2's "editing a confirmed job
after it has an active scoring run marks that run invalidated") is
deliberately not implemented here - it depends on `scoring_runs`
persistence, which doesn't exist until Stage 8. Wiring it in before
there are any runs to invalidate would be untestable, unverifiable
scaffolding.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from db.models import Job
from db.models import JobRequirement as JobRequirementRow
from db.models import JobResponsibility as JobResponsibilityRow
from db.repositories import get_company_by_id
from domain.enums import JobStatus
from domain.exceptions import ValidationError
from parsing.job_parser import parse_job_description


def create_job(
    session: Session,
    *,
    company_id: UUID,
    raw_description: str,
    title: str | None = None,
) -> Job:
    """Persists a raw, unparsed, unconfirmed Job row linked to an
    existing company. Parsing (`parse_and_persist_job`) is a separate,
    later step - matching the real UI flow (Section 15.2 Page 1: the
    textarea is filled in before "Analyze Description" is clicked)."""
    company = get_company_by_id(session, company_id)
    if company is None:
        raise ValueError(f"Company {company_id} not found")

    job = Job(
        company_id=company_id,
        raw_description=raw_description,
        title=title,
        status="open",
        confirmed=False,
        parser_version=None,
    )
    session.add(job)
    session.commit()
    return job


def parse_and_persist_job(
    session: Session, job_id: UUID, *, taxonomy: Any, scoring_config: Any
) -> Job:
    """Runs Section 10's parse_job_description() against the stored
    raw_description and persists the resulting requirements/
    responsibilities as rows. Parsing warnings are not persisted -
    Section 6.1 has no table for them; like the confirmation page
    itself, they're a transient view over a freshly-parsed JobProfile,
    never round-tripped through the DB."""
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    profile = parse_job_description(
        job.raw_description,
        title=job.title,
        taxonomy=taxonomy,
        scoring_config=scoring_config,
    )

    for requirement in (
        profile.required_qualifications + profile.preferred_qualifications
    ):
        session.add(
            JobRequirementRow(
                id=requirement.requirement_id,
                job_id=job.id,
                requirement_type=requirement.type,
                canonical_name=requirement.canonical_name,
                original_text=requirement.original_text,
                importance=requirement.importance,
                confidence=requirement.confidence,
                is_required=requirement.required,
                allows_equivalent_experience=requirement.allows_equivalent_experience,
                equivalent_years=requirement.equivalent_years,
                degree_level=requirement.degree_level,
                field_of_study=requirement.field_of_study,
            )
        )

    for responsibility in profile.responsibilities:
        session.add(
            JobResponsibilityRow(
                id=responsibility.responsibility_id,
                job_id=job.id,
                original_text=responsibility.original_text,
                normalized_text=responsibility.normalized_text,
                position=responsibility.position,
            )
        )

    job.title = profile.title
    job.minimum_relevant_years = profile.minimum_relevant_years
    job.parser_version = profile.parser_version
    session.commit()
    return job


def confirm_job(session: Session, job_id: UUID) -> Job:
    """Section 10.8: "Confirm and Continue" freezes the profile. Same
    "nothing scoreable" guard as parsing.job_parser.confirm_job_profile,
    applied to the persisted rows rather than an in-memory JobProfile."""
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    if not job.requirements and not job.responsibilities:
        raise ValidationError(
            "Nothing scoreable in this job profile - please add requirements or "
            "responsibilities before confirming."
        )

    job.confirmed = True
    session.commit()
    return job


def update_job_status(session: Session, job_id: UUID, status: JobStatus) -> Job:
    """Post-Stage-7 addendum (pre-Stage-9 infrastructure): moves a job
    through open -> closed -> archived. Independent of `confirmed` -
    a job can be closed or archived whether or not it was ever scored."""
    job = session.get(Job, job_id)
    if job is None:
        raise ValueError(f"Job {job_id} not found")

    job.status = status
    session.commit()
    return job
