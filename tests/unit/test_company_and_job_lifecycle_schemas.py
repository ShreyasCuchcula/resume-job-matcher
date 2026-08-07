"""Unit tests for the Company schema and JobProfile's company/status/
expires_at fields (post-Stage-7 addendum, pre-Stage-9 infrastructure -
SPECIFICATION.md Section 6.3, not part of the original 10-stage plan)."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from domain.schemas import Company, JobProfile


class TestCompanySchema:
    def test_minimal_company_defaults(self):
        company = Company(name="Acme Corp")
        assert company.name == "Acme Corp"
        assert company.industry is None
        assert isinstance(company.id, type(uuid4()))
        assert isinstance(company.created_at, datetime)
        assert isinstance(company.updated_at, datetime)

    def test_industry_is_optional(self):
        company = Company(name="Acme Corp", industry="Software")
        assert company.industry == "Software"

    def test_empty_name_is_rejected(self):
        with pytest.raises(ValidationError):
            Company(name="")

    def test_whitespace_only_name_is_rejected(self):
        with pytest.raises(ValidationError):
            Company(name="   ")

    def test_unknown_field_is_rejected(self):
        """_StrictModel: extra='forbid' everywhere in this schema file."""
        with pytest.raises(ValidationError):
            Company(name="Acme Corp", unknown_field="x")


class TestJobProfileLifecycleFields:
    def _job(self, **overrides) -> JobProfile:
        defaults = dict(
            title="Data Analyst",
            raw_description="x" * 150,
            parser_version="test",
        )
        defaults.update(overrides)
        return JobProfile(**defaults)

    def test_defaults_are_backward_compatible(self):
        """Every existing caller across Stages 3-7 constructs JobProfile
        without these fields - they must default sanely."""
        job = self._job()
        assert job.company_id is None
        assert job.status == "open"
        assert job.expires_at is None

    def test_company_id_accepts_a_uuid(self):
        company_id = uuid4()
        job = self._job(company_id=company_id)
        assert job.company_id == company_id

    def test_status_accepts_all_three_lifecycle_values(self):
        for status in ("open", "closed", "archived"):
            assert self._job(status=status).status == status

    def test_invalid_status_is_rejected(self):
        with pytest.raises(ValidationError):
            self._job(status="deleted")

    def test_expires_at_accepts_a_datetime(self):
        expires = datetime(2027, 1, 1)
        job = self._job(expires_at=expires)
        assert job.expires_at == expires
