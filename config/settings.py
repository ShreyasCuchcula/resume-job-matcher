"""Typed, validated application configuration (SPECIFICATION.md Section 7.2).

Two independent things get loaded and validated here:

1. `Settings` - environment variables (`.env`): where the database and
   uploads live, which scoring config file to read, log verbosity.
2. `ScoringConfig` / `TaxonomyBundle` - the YAML/JSON configuration
   that drives the scoring engine itself.

`get_app_config()` is the fail-fast entrypoint: the app refuses to
start if any weight is negative, weights don't sum to 1.0 (+/- 1e-9),
any threshold falls outside [0, 1], label boundaries aren't strictly
descending, a taxonomy file is missing or not valid JSON, an alias
collides with another entry's canonical name, or the taxonomy VERSION
file is missing.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from domain.exceptions import ValidationError

_WEIGHT_SUM_TOLERANCE = 1e-9

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# scoring.yaml
# ---------------------------------------------------------------------------


class WeightsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required: float = Field(ge=0.0)
    experience: float = Field(ge=0.0)
    responsibility: float = Field(ge=0.0)
    preferred: float = Field(ge=0.0)

    @model_validator(mode="after")
    def _sum_to_one(self) -> "WeightsConfig":
        total = self.required + self.experience + self.responsibility + self.preferred
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"weights must sum to 1.0 (+/- 1e-9), got {total}")
        return self


class ResponsibilityMatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_similarity: float = Field(ge=0.0, le=1.0)
    role_relevance_threshold: float = Field(ge=0.0, le=1.0)
    ngram_min: int = Field(ge=1)
    ngram_max: int = Field(ge=1)
    sublinear_tf: bool

    @model_validator(mode="after")
    def _ngram_range_is_ordered(self) -> "ResponsibilityMatchingConfig":
        if self.ngram_min > self.ngram_max:
            raise ValueError("ngram_min must be <= ngram_max")
        return self


class EvidenceStrengthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    demonstrated: float = Field(ge=0.0, le=1.0)
    summary: float = Field(ge=0.0, le=1.0)
    skills_section: float = Field(ge=0.0, le=1.0)
    related_default: float = Field(ge=0.0, le=1.0)


class JobParsingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    auto_include_confidence: float = Field(ge=0.0, le=1.0)
    review_confidence: float = Field(ge=0.0, le=1.0)
    min_description_chars: int = Field(ge=0)
    max_description_chars: int = Field(gt=0)

    @model_validator(mode="after")
    def _bounds_are_ordered(self) -> "JobParsingConfig":
        if self.review_confidence > self.auto_include_confidence:
            raise ValueError("review_confidence must be <= auto_include_confidence")
        if self.min_description_chars >= self.max_description_chars:
            raise ValueError("min_description_chars must be < max_description_chars")
        return self


class UploadsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    maximum_resume_mb: int = Field(gt=0)
    allowed_extensions: list[str] = Field(min_length=1)
    min_extracted_chars: int = Field(ge=0)


class LabelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strong: float = Field(ge=0.0, le=100.0)
    good: float = Field(ge=0.0, le=100.0)
    possible: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _boundaries_strictly_descending(self) -> "LabelsConfig":
        if not (self.strong > self.good > self.possible):
            raise ValueError("labels.strong > labels.good > labels.possible must hold")
        return self


class ScoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scoring_version: str
    weights: WeightsConfig
    responsibility_matching: ResponsibilityMatchingConfig
    evidence_strength: EvidenceStrengthConfig
    job_parsing: JobParsingConfig
    uploads: UploadsConfig
    labels: LabelsConfig


def load_scoring_config(path: Path) -> ScoringConfig:
    if not path.is_file():
        raise ValidationError(f"Scoring config not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationError(f"Scoring config at {path} is not valid YAML: {exc}") from exc
    try:
        return ScoringConfig.model_validate(raw)
    except PydanticValidationError as exc:
        raise ValidationError(f"Scoring config at {path} failed validation:\n{exc}") from exc


# ---------------------------------------------------------------------------
# config/taxonomy/*
# ---------------------------------------------------------------------------

_ALIAS_BEARING_TAXONOMIES = ("skills.json", "certifications.json", "titles.json")


class TaxonomyBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    skills: dict[str, Any]
    degrees: dict[str, Any]
    fields: dict[str, Any]
    certifications: dict[str, Any]
    titles: dict[str, Any]
    phrase_normalization: dict[str, str]


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ValidationError(f"Taxonomy file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Taxonomy file {path} is not valid JSON: {exc}") from exc


def _validate_alias_collision_free(filename: str, taxonomy: dict[str, Any]) -> None:
    """Alias -> canonical map must be collision-free (Section 7.3): no
    alias may equal a different entry's canonical name, and no alias
    may be claimed by two different canonical entries."""
    canonicals = set(taxonomy.keys())
    claimed: dict[str, str] = {}
    for canonical, entry in taxonomy.items():
        for alias in entry.get("aliases", []):
            if alias in canonicals and alias != canonical:
                raise ValidationError(
                    f"{filename}: alias '{alias}' (of '{canonical}') collides with "
                    f"an existing canonical name"
                )
            if alias in claimed and claimed[alias] != canonical:
                raise ValidationError(
                    f"{filename}: alias '{alias}' is claimed by both "
                    f"'{claimed[alias]}' and '{canonical}'"
                )
            claimed[alias] = canonical


def load_taxonomies(taxonomy_dir: Path) -> TaxonomyBundle:
    version_path = taxonomy_dir / "VERSION"
    if not version_path.is_file():
        raise ValidationError(f"Taxonomy VERSION file not found: {version_path}")
    version = version_path.read_text(encoding="utf-8").strip()
    if not version:
        raise ValidationError(f"Taxonomy VERSION file at {version_path} is empty")

    loaded = {
        "skills": _load_json(taxonomy_dir / "skills.json"),
        "degrees": _load_json(taxonomy_dir / "degrees.json"),
        "fields": _load_json(taxonomy_dir / "fields.json"),
        "certifications": _load_json(taxonomy_dir / "certifications.json"),
        "titles": _load_json(taxonomy_dir / "titles.json"),
        "phrase_normalization": _load_json(taxonomy_dir / "phrase_normalization.json"),
    }

    for filename in _ALIAS_BEARING_TAXONOMIES:
        key = filename.removesuffix(".json")
        _validate_alias_collision_free(filename, loaded[key])

    try:
        return TaxonomyBundle(version=version, **loaded)
    except PydanticValidationError as exc:
        raise ValidationError(f"Taxonomy bundle at {taxonomy_dir} failed validation:\n{exc}") from exc


# ---------------------------------------------------------------------------
# Environment settings (.env)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./resume_matcher.db"
    upload_dir: Path = Path("./uploads")
    scoring_config_path: Path = Path("./config/scoring.yaml")
    taxonomy_dir: Path = Path("./config/taxonomy")
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Combined, fail-fast application config
# ---------------------------------------------------------------------------


class AppConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    settings: Settings
    scoring: ScoringConfig
    taxonomy: TaxonomyBundle


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    """Load and validate everything the app needs to run. Cached after
    the first call; call `get_app_config.cache_clear()` (e.g. in test
    fixtures) to force a reload with different environment variables."""
    settings = Settings()
    scoring = load_scoring_config(settings.scoring_config_path)
    taxonomy = load_taxonomies(settings.taxonomy_dir)
    return AppConfig(settings=settings, scoring=scoring, taxonomy=taxonomy)
