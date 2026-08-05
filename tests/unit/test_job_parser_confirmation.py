"""Unit tests for parsing/job_parser.py's confirmation-page data
contract (SPECIFICATION.md Section 10.8)."""

from __future__ import annotations

import pytest

from domain.exceptions import ValidationError
from domain.schemas import JobProfile, JobRequirement, JobResponsibility
from parsing.job_parser import (
    add_requirement,
    confirm_job_profile,
    delete_requirement,
    edit_requirement,
    reclassify_requirement,
)


def _sql_requirement(required: bool = True) -> JobRequirement:
    return JobRequirement(
        type="skill",
        canonical_name="sql",
        original_text="Must have SQL.",
        importance=3,
        confidence=0.9,
        required=required,
    )


def _profile_with(**overrides) -> JobProfile:
    base = dict(
        title="Data Analyst",
        raw_description="x" * 150,
        required_qualifications=[_sql_requirement()],
        parser_version="test",
    )
    base.update(overrides)
    return JobProfile(**base)


def test_confirm_sets_confirmed_true():
    profile = _profile_with()
    confirmed = confirm_job_profile(profile)
    assert confirmed.confirmed is True
    assert profile.confirmed is False  # original untouched (pure function)


def test_confirm_empty_profile_raises():
    profile = _profile_with(required_qualifications=[])
    with pytest.raises(ValidationError, match="Nothing scoreable"):
        confirm_job_profile(profile)


def test_confirm_profile_with_only_responsibilities_succeeds():
    resp = JobResponsibility(
        original_text="Build dashboards.",
        normalized_text="build dashboard.",
        position=0,
    )
    profile = _profile_with(required_qualifications=[], responsibilities=[resp])
    confirmed = confirm_job_profile(profile)
    assert confirmed.confirmed is True


def test_add_requirement_appends_to_correct_list():
    profile = _profile_with(confirmed=True)
    new_item = JobRequirement(
        type="skill",
        canonical_name="python",
        original_text="added",
        importance=1,
        confidence=0.9,
        required=False,
    )
    updated = add_requirement(profile, new_item)
    assert len(updated.preferred_qualifications) == 1
    assert updated.preferred_qualifications[0].canonical_name == "python"
    # editing a confirmed profile creates a new unconfirmed revision (Section 10.8)
    assert updated.confirmed is False


def test_edit_requirement_updates_fields():
    profile = _profile_with()
    requirement_id = profile.required_qualifications[0].requirement_id
    updated = edit_requirement(profile, requirement_id, importance=1)
    assert updated.required_qualifications[0].importance == 1
    assert updated.confirmed is False


def test_edit_requirement_unknown_id_raises():
    profile = _profile_with()
    with pytest.raises(ValidationError, match="No requirement found"):
        edit_requirement(profile, __import__("uuid").uuid4(), importance=1)


def test_delete_requirement_removes_item():
    profile = _profile_with()
    requirement_id = profile.required_qualifications[0].requirement_id
    updated = delete_requirement(profile, requirement_id)
    assert updated.required_qualifications == []
    assert updated.confirmed is False


def test_reclassify_moves_between_required_and_preferred():
    profile = _profile_with()
    requirement_id = profile.required_qualifications[0].requirement_id
    updated = reclassify_requirement(profile, requirement_id, required=False)
    assert updated.required_qualifications == []
    assert len(updated.preferred_qualifications) == 1
    assert updated.preferred_qualifications[0].required is False
    assert updated.preferred_qualifications[0].requirement_id == requirement_id


def test_reclassify_preserves_other_fields():
    profile = _profile_with()
    requirement_id = profile.required_qualifications[0].requirement_id
    updated = reclassify_requirement(profile, requirement_id, required=False)
    moved = updated.preferred_qualifications[0]
    assert moved.canonical_name == "sql"
    assert moved.importance == 3
    assert moved.confidence == 0.9
