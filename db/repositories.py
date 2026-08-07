"""Typed query/persist functions per aggregate (SPECIFICATION.md
Section 4's documented file layout - not built until now, since no
earlier stage needed job-level DB persistence; Stages 0-7 worked on
`domain.schemas` pydantic objects directly, and Stage 2's ingestion
went straight through `db.models` with no repository layer).

Post-Stage-7 addendum (pre-Stage-9 infrastructure, not part of the
original 10-stage plan - SPECIFICATION.md Section 6.3): the first
functions here are Company-scoped, added alongside the companies
table/job-lifecycle fields for Stage 9's UI to build on.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from db.models import Company, Job


def get_company_by_id(session: Session, company_id: UUID) -> Company | None:
    return session.get(Company, company_id)


def get_jobs_by_company(session: Session, company_id: UUID) -> list[Job]:
    return (
        session.query(Job)
        .filter_by(company_id=company_id)
        .order_by(Job.created_at.desc())
        .all()
    )


def create_company(session: Session, name: str, industry: str | None = None) -> Company:
    company = Company(name=name, industry=industry)
    session.add(company)
    session.commit()
    return company
