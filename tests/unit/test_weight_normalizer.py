"""Unit tests for matching/weight_normalizer.py (SPECIFICATION.md
Section 13.5, Section 18.1 fixtures)."""

from __future__ import annotations

import pytest

from domain.exceptions import UnscorableJobError
from matching.weight_normalizer import normalize_weights

DEFAULT_WEIGHTS = {
    "required": 0.45,
    "experience": 0.20,
    "responsibility": 0.20,
    "preferred": 0.15,
}


class TestAllComponentsPresent:
    def test_defaults_unchanged_when_everything_applicable(self):
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert weights == DEFAULT_WEIGHTS

    def test_weights_sum_to_1_within_tolerance(self):
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestPreferredAbsent:
    """Section 13.5 fixture: preferred absent -> 0.45/0.85, 0.20/0.85,
    0.20/0.85 = 0.5294 / 0.2353 / 0.2353."""

    def test_redistributes_to_the_documented_fixture(self):
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": None,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert "preferred" not in weights
        assert round(weights["required"], 4) == 0.5294
        assert round(weights["experience"], 4) == 0.2353
        assert round(weights["responsibility"], 4) == 0.2353
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestExperienceAbsent:
    def test_redistributes_across_the_other_three(self):
        scores = {
            "required": 94.29,
            "experience": None,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert "experience" not in weights
        total = 0.45 + 0.20 + 0.15
        assert weights["required"] == pytest.approx(0.45 / total)
        assert weights["responsibility"] == pytest.approx(0.20 / total)
        assert weights["preferred"] == pytest.approx(0.15 / total)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestResponsibilityAbsent:
    def test_redistributes_across_the_other_three(self):
        scores = {
            "required": 94.29,
            "experience": 83.33,
            "responsibility": None,
            "preferred": 72.00,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert "responsibility" not in weights
        total = 0.45 + 0.20 + 0.15
        assert weights["required"] == pytest.approx(0.45 / total)
        assert weights["experience"] == pytest.approx(0.20 / total)
        assert weights["preferred"] == pytest.approx(0.15 / total)
        assert abs(sum(weights.values()) - 1.0) < 1e-9


class TestAllNoneRaisesUnscorable:
    def test_all_none_raises_unscorable_job_error(self):
        scores = {
            "required": None,
            "experience": None,
            "responsibility": None,
            "preferred": None,
        }
        with pytest.raises(UnscorableJobError):
            normalize_weights(scores, DEFAULT_WEIGHTS)


class TestZeroIsApplicableNotInapplicable:
    def test_zero_score_keeps_its_weight_unlike_none(self):
        """`0` = applicable and keeps its weight; `None` = inapplicable
        and redistributes - the two must never be conflated."""
        scores = {
            "required": 0.0,
            "experience": 83.33,
            "responsibility": 66.33,
            "preferred": 72.00,
        }
        weights = normalize_weights(scores, DEFAULT_WEIGHTS)
        assert weights == DEFAULT_WEIGHTS
