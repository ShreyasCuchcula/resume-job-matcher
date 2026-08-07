"""Unit tests for matching/responsibility_scorer.py (SPECIFICATION.md
Section 12, Section 18.1 fixtures)."""

from __future__ import annotations

from uuid import uuid4

from domain.schemas import EvidenceBullet, JobResponsibility
from matching.responsibility_scorer import (
    MINIMUM_SIMILARITY_DEFAULT,
    build_vectorizer,
    calculate_responsibility_score,
    responsibility_score_from_adjusted,
)


def _responsibility(text: str, position: int = 0) -> JobResponsibility:
    return JobResponsibility(
        original_text=text, normalized_text=text.lower(), position=position
    )


def _bullet(text: str, section_type: str = "employment") -> EvidenceBullet:
    return EvidenceBullet(
        employment_id=uuid4() if section_type == "employment" else None,
        section_type=section_type,
        original_text=text,
        normalized_text=text.lower(),
    )


class TestResponsibilityScoreFromAdjustedFixture:
    """Section 12.5: bests 0.76, 0.65, 0.58 -> 100 x 1.99/3 = 66.33."""

    def test_fixture_reproduces_66_33_exactly(self):
        assert responsibility_score_from_adjusted([0.76, 0.65, 0.58]) == 66.33

    def test_single_perfect_match_is_100(self):
        assert responsibility_score_from_adjusted([1.0]) == 100.00

    def test_all_zero_is_zero(self):
        assert responsibility_score_from_adjusted([0.0, 0.0]) == 0.00


class TestMinimumSimilarityThreshold:
    """Section 16: 0.19 -> 0.0, 0.20 -> kept (inclusive boundary)."""

    def _score_via_fake_vectorizer(self, similarity: float) -> float:
        class _FakeVectorizer:
            def transform(self, texts):
                import numpy as np

                # One responsibility, one bullet: force the cosine
                # similarity to exactly `similarity` via parallel/
                # scaled unit vectors along orthogonal-then-shared axes.
                if len(texts) == 1 and texts == ["responsibility"]:
                    return np.array([[1.0, 0.0]])
                return np.array([[similarity, (1 - similarity**2) ** 0.5]])

        return calculate_responsibility_score(
            [_responsibility("Responsibility", position=0)],
            [_bullet("Bullet")],
            _FakeVectorizer(),
        ).score

    def test_below_threshold_scores_zero(self):
        # 0.19 similarity -> adjusted 0.0 -> responsibility_score 0.00
        result = self._score_via_fake_vectorizer(0.19)
        assert result == 0.00

    def test_at_threshold_is_kept(self):
        result = self._score_via_fake_vectorizer(0.20)
        assert result == 20.00  # 100 * mean([0.20])


class TestEdgeCases:
    def test_no_job_responsibilities_is_none_not_zero(self):
        vectorizer = build_vectorizer().fit(["some text", "other text"])
        result = calculate_responsibility_score(
            [], [_bullet("Did a thing.")], vectorizer
        )
        assert result.score is None
        assert result.evidence == []
        assert result.warnings == []

    def test_zero_bullets_is_zero_not_none_with_warning(self):
        vectorizer = build_vectorizer().fit(["build pipelines", "query data"])
        responsibilities = [_responsibility("Build and maintain ETL pipelines.")]
        result = calculate_responsibility_score(responsibilities, [], vectorizer)
        assert result.score == 0.00
        assert len(result.evidence) == 1
        assert (
            result.evidence[0].responsibility_id
            == responsibilities[0].responsibility_id
        )
        assert any(w.code == "NO_EVIDENCE_BULLETS" for w in result.warnings)

    def test_every_responsibility_appears_in_evidence(self):
        vectorizer = build_vectorizer().fit(
            ["build pipelines", "query data", "write reports", "unrelated retail task"]
        )
        responsibilities = [
            _responsibility("Build pipelines.", position=0),
            _responsibility("Query data.", position=1),
            _responsibility("Write reports.", position=2),
        ]
        bullets = [_bullet("Built ETL pipelines for the warehouse.")]
        result = calculate_responsibility_score(responsibilities, bullets, vectorizer)
        assert len(result.evidence) == 3
        assert {e.responsibility_id for e in result.evidence} == {
            r.responsibility_id for r in responsibilities
        }

    def test_evidence_section_reflects_the_matched_bullets_own_section(self):
        vectorizer = build_vectorizer().fit(["build pipelines", "run experiments"])
        responsibilities = [_responsibility("Build pipelines.")]
        bullets = [_bullet("Built pipelines.", section_type="project")]
        result = calculate_responsibility_score(responsibilities, bullets, vectorizer)
        assert result.evidence[0].evidence_section == "project"

    def test_default_minimum_similarity_matches_section_12_4(self):
        assert MINIMUM_SIMILARITY_DEFAULT == 0.20
