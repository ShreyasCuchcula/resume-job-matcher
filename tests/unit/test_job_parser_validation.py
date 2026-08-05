"""Unit tests for parsing/job_parser.py's Section 10.1 validation and
Section 10.5 confidence banding."""

from __future__ import annotations

import pytest

from config.settings import JobParsingConfig
from domain.exceptions import ValidationError
from domain.schemas import JobRequirement
from parsing.job_parser import (
    confidence_band,
    scoreable_requirements,
    validate_description,
)

JOB_PARSING_CONFIG = JobParsingConfig(
    auto_include_confidence=0.80,
    review_confidence=0.60,
    min_description_chars=100,
    max_description_chars=50000,
)


def test_empty_description_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_description("", JOB_PARSING_CONFIG)


def test_whitespace_only_description_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_description("   \n\t  ", JOB_PARSING_CONFIG)


def test_too_short_description_rejected():
    with pytest.raises(ValidationError, match="too short"):
        validate_description("Short description.", JOB_PARSING_CONFIG)


def test_too_long_description_rejected():
    with pytest.raises(ValidationError, match="too long"):
        validate_description("x" * 50001, JOB_PARSING_CONFIG)


def test_mostly_symbols_rejected():
    with pytest.raises(ValidationError, match="non-text symbols"):
        validate_description("!@#$%^&*()_+-=[]{}|;:,.<>?" * 10, JOB_PARSING_CONFIG)


def test_valid_description_passes():
    validate_description("A" * 150, JOB_PARSING_CONFIG)  # must not raise


def test_description_at_exact_minimum_length_passes():
    validate_description("A" * 100, JOB_PARSING_CONFIG)  # must not raise


def test_description_at_exact_maximum_length_passes():
    validate_description("A" * 50000, JOB_PARSING_CONFIG)  # must not raise


# ---------------------------------------------------------------------------
# Confidence banding (Section 10.5)
# ---------------------------------------------------------------------------


def test_confidence_band_boundaries():
    assert confidence_band(0.80, JOB_PARSING_CONFIG) == "include"
    assert confidence_band(1.00, JOB_PARSING_CONFIG) == "include"
    assert confidence_band(0.79, JOB_PARSING_CONFIG) == "review"
    assert confidence_band(0.60, JOB_PARSING_CONFIG) == "review"
    assert confidence_band(0.59, JOB_PARSING_CONFIG) == "exclude"
    assert confidence_band(0.00, JOB_PARSING_CONFIG) == "exclude"


def _requirement(confidence: float) -> JobRequirement:
    return JobRequirement(
        type="skill",
        canonical_name="sql",
        original_text="x",
        importance=2,
        confidence=confidence,
        required=True,
    )


def test_scoreable_requirements_drops_only_excluded_band():
    requirements = [_requirement(0.9), _requirement(0.65), _requirement(0.3)]
    result = scoreable_requirements(requirements, JOB_PARSING_CONFIG)
    assert len(result) == 2
    assert all(r.confidence >= 0.60 for r in result)
