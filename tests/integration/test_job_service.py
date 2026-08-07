"""Integration tests for services/job_service.py (post-Stage-7
addendum, pre-Stage-9 infrastructure - SPECIFICATION.md Section 6.3,
not part of the original 10-stage plan). Uses the in-memory SQLite
`db_session` fixture and a real job description + real taxonomy/
scoring config, matching this project's established integration-test
convention (see tests/integration/test_qualification_scoring_integration.py).
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from config.settings import get_app_config
from db.models import Company
from db.repositories import create_company
from domain.exceptions import ValidationError
from services.job_service import (
    confirm_job,
    create_job,
    parse_and_persist_job,
    update_job_status,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JOB_TEXT = (
    REPO_ROOT / "sample_data" / "jobs" / "job_01_data_analyst_standard.txt"
).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_config():
    return get_app_config()


@pytest.fixture
def company(db_session) -> Company:
    return create_company(db_session, "Acme Corp")


class TestCreateJob:
    def test_creates_an_unconfirmed_open_job_linked_to_the_company(
        self, db_session, company
    ):
        job = create_job(
            db_session,
            company_id=company.id,
            raw_description=JOB_TEXT,
            title="Data Analyst",
        )
        assert job.id is not None
        assert job.company_id == company.id
        assert job.status == "open"
        assert job.confirmed is False
        assert job.parser_version is None

    def test_unknown_company_id_is_rejected(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            create_job(db_session, company_id=uuid4(), raw_description=JOB_TEXT)


class TestParseAndPersistJob:
    def test_persists_requirements_and_responsibilities(
        self, db_session, company, app_config
    ):
        job = create_job(db_session, company_id=company.id, raw_description=JOB_TEXT)
        parsed = parse_and_persist_job(
            db_session,
            job.id,
            taxonomy=app_config.taxonomy,
            scoring_config=app_config.scoring,
        )
        assert parsed.parser_version is not None
        assert parsed.minimum_relevant_years == 2.0
        assert len(parsed.requirements) > 0
        assert len(parsed.responsibilities) > 0

    def test_unknown_job_id_is_rejected(self, db_session, app_config):
        with pytest.raises(ValueError, match="not found"):
            parse_and_persist_job(
                db_session,
                uuid4(),
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )


class TestConfirmJob:
    def test_confirming_an_unparsed_job_is_rejected(self, db_session, company):
        job = create_job(db_session, company_id=company.id, raw_description=JOB_TEXT)
        with pytest.raises(ValidationError):
            confirm_job(db_session, job.id)

    def test_confirming_a_parsed_job_succeeds(self, db_session, company, app_config):
        job = create_job(db_session, company_id=company.id, raw_description=JOB_TEXT)
        parse_and_persist_job(
            db_session,
            job.id,
            taxonomy=app_config.taxonomy,
            scoring_config=app_config.scoring,
        )
        confirmed = confirm_job(db_session, job.id)
        assert confirmed.confirmed is True

    def test_unknown_job_id_is_rejected(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            confirm_job(db_session, uuid4())


class TestUpdateJobStatus:
    def test_moves_through_the_lifecycle(self, db_session, company):
        job = create_job(db_session, company_id=company.id, raw_description=JOB_TEXT)
        assert update_job_status(db_session, job.id, "closed").status == "closed"
        assert update_job_status(db_session, job.id, "archived").status == "archived"

    def test_unknown_job_id_is_rejected(self, db_session):
        with pytest.raises(ValueError, match="not found"):
            update_job_status(db_session, uuid4(), "closed")
