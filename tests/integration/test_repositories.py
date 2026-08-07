"""Integration tests for db/repositories.py's company-scoped helpers
(post-Stage-7 addendum, pre-Stage-9 infrastructure - SPECIFICATION.md
Section 6.3, not part of the original 10-stage plan)."""

from __future__ import annotations

from uuid import uuid4

from db.models import Job
from db.repositories import create_company, get_company_by_id, get_jobs_by_company


class TestCreateCompany:
    def test_creates_and_persists_a_company(self, db_session):
        company = create_company(db_session, "Acme Corp", industry="Software")
        assert company.id is not None
        assert get_company_by_id(db_session, company.id) is not None

    def test_industry_defaults_to_none(self, db_session):
        company = create_company(db_session, "Acme Corp")
        assert company.industry is None


class TestGetCompanyById:
    def test_returns_none_for_unknown_id(self, db_session):
        assert get_company_by_id(db_session, uuid4()) is None

    def test_returns_the_matching_company(self, db_session):
        company = create_company(db_session, "Acme Corp")
        found = get_company_by_id(db_session, company.id)
        assert found is not None
        assert found.name == "Acme Corp"


class TestGetJobsByCompany:
    def test_returns_empty_list_for_company_with_no_jobs(self, db_session):
        company = create_company(db_session, "Acme Corp")
        assert get_jobs_by_company(db_session, company.id) == []

    def test_returns_only_that_companys_jobs_newest_first(self, db_session):
        company_a = create_company(db_session, "Acme Corp")
        company_b = create_company(db_session, "Globex Corp")

        job_a1 = Job(
            company=company_a, raw_description="x" * 150, parser_version="test"
        )
        job_a2 = Job(
            company=company_a, raw_description="y" * 150, parser_version="test"
        )
        job_b1 = Job(
            company=company_b, raw_description="z" * 150, parser_version="test"
        )
        db_session.add_all([job_a1, job_a2, job_b1])
        db_session.commit()

        jobs = get_jobs_by_company(db_session, company_a.id)
        assert {job.id for job in jobs} == {job_a1.id, job_a2.id}
        assert job_b1 not in jobs
