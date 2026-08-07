"""Integration tests for the Company/Job ORM models (post-Stage-7
addendum, pre-Stage-9 infrastructure - SPECIFICATION.md Section 6.3,
not part of the original 10-stage plan). Uses the in-memory SQLite
`db_session` fixture from tests/conftest.py, which applies the full
schema via `Base.metadata.create_all()` - the same schema the Alembic
migration produces, verified separately in
db/migrations/versions/0003_add_companies_and_job_lifecycle.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import Company, Job


def _job(**overrides) -> Job:
    defaults = dict(raw_description="x" * 150, parser_version="test")
    defaults.update(overrides)
    return Job(**defaults)


class TestCompanyModel:
    def test_create_company_minimal(self, db_session):
        company = Company(name="Acme Corp")
        db_session.add(company)
        db_session.commit()
        assert company.id is not None
        assert company.industry is None
        assert company.created_at is not None
        assert company.updated_at is not None

    def test_name_must_be_unique(self, db_session):
        db_session.add(Company(name="Acme Corp"))
        db_session.commit()
        db_session.add(Company(name="Acme Corp"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestJobCompanyRelationship:
    def test_job_defaults_to_open_status_and_no_company(self, db_session):
        job = _job()
        db_session.add(job)
        db_session.commit()
        assert job.status == "open"
        assert job.company_id is None
        assert job.company is None

    def test_job_linked_to_company(self, db_session):
        company = Company(name="Acme Corp")
        job = _job(company=company)
        db_session.add(job)
        db_session.commit()
        assert job.company_id == company.id
        assert company.jobs == [job]

    def test_invalid_status_violates_check_constraint(self, db_session):
        job = _job(status="deleted")
        db_session.add(job)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_deleting_company_cascades_to_its_jobs(self, db_session):
        company = Company(name="Acme Corp")
        job = _job(company=company)
        db_session.add(job)
        db_session.commit()
        job_id = job.id

        db_session.delete(company)
        db_session.commit()

        assert db_session.get(Job, job_id) is None

    def test_expires_at_is_optional(self, db_session):
        job = _job()
        db_session.add(job)
        db_session.commit()
        assert job.expires_at is None
