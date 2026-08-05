"""Unit tests for matching/scoring_engine.py (SPECIFICATION.md Section
10.8's "unconfirmed jobs cannot be scored" hard assertion, Section 11
required/preferred dispatch)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.schemas import CandidateProfile, JobProfile, JobRequirement
from matching.scoring_engine import (
    score_preferred_qualifications,
    score_required_qualifications,
)

TAXONOMY = SimpleNamespace(
    skills={"sql": {"aliases": [], "category": "database", "related_skills": {}}},
    degrees={"ladder": ["high_school", "associate", "bachelor", "master", "doctorate"]},
    fields={},
    certifications={},
)


def _candidate() -> CandidateProfile:
    return CandidateProfile(
        display_identifier="Candidate 001",
        file_hash="x" * 64,
        raw_resume_text="",
        scoring_text_available=True,
        parser_version="test",
    )


def _requirement(canonical_name: str, required: bool) -> JobRequirement:
    return JobRequirement(
        type="skill",
        canonical_name=canonical_name,
        original_text=f"Requires {canonical_name}",
        importance=2,
        confidence=0.9,
        required=required,
    )


def _job(*, confirmed: bool) -> JobProfile:
    return JobProfile(
        title="Data Analyst",
        raw_description="x" * 150,
        required_qualifications=[_requirement("sql", True)],
        preferred_qualifications=[],
        parser_version="test",
        confirmed=confirmed,
    )


class TestUnconfirmedJobCannotBeScored:
    def test_score_required_raises_assertion_on_unconfirmed_job(self):
        with pytest.raises(AssertionError):
            score_required_qualifications(_job(confirmed=False), _candidate(), TAXONOMY)

    def test_score_preferred_raises_assertion_on_unconfirmed_job(self):
        with pytest.raises(AssertionError):
            score_preferred_qualifications(
                _job(confirmed=False), _candidate(), TAXONOMY
            )


class TestConfirmedJobScoring:
    def test_score_required_uses_required_qualifications_list(self):
        job = _job(confirmed=True)
        result = score_required_qualifications(job, _candidate(), TAXONOMY)
        assert result.score is not None
        assert result.missing[0].canonical_name == "sql"

    def test_score_preferred_is_none_when_no_preferred_items(self):
        job = _job(confirmed=True)
        result = score_preferred_qualifications(job, _candidate(), TAXONOMY)
        assert result.score is None
