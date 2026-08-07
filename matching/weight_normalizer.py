"""Dynamic weight normalization (SPECIFICATION.md Section 13.5)."""

from __future__ import annotations

from domain.exceptions import UnscorableJobError


def normalize_weights(
    scores: dict[str, float | None], default_weights: dict[str, float]
) -> dict[str, float]:
    """`None` = inapplicable and redistributes its weight across the
    remaining applicable components; `0` (or any real number) =
    applicable and keeps its default weight. Raises
    `UnscorableJobError` when every component is inapplicable - there
    is nothing left to score against."""
    applicable = {
        key: weight
        for key, weight in default_weights.items()
        if scores.get(key) is not None
    }
    total = sum(applicable.values())
    if total == 0:
        raise UnscorableJobError("No applicable scoring components")
    return {key: weight / total for key, weight in applicable.items()}
