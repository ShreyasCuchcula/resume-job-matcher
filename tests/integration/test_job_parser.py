"""Integration tests for the full job-parsing pipeline
(parsing/job_parser.py::parse_job_description) against all 6 real
synthetic job descriptions and the Section 10.1 / 18.1 end-to-end
scenarios (SPECIFICATION.md Section 10, Section 18.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import get_app_config
from domain.exceptions import ValidationError
from parsing.job_parser import parse_job_description

SAMPLE_JOBS_DIR = Path(__file__).resolve().parent.parent.parent / "sample_data" / "jobs"


@pytest.fixture(scope="module")
def app_config():
    return get_app_config()


def _parse(filename: str, app_config, title: str | None = None):
    text = (SAMPLE_JOBS_DIR / filename).read_text(encoding="utf-8")
    return parse_job_description(
        text,
        title=title,
        taxonomy=app_config.taxonomy,
        scoring_config=app_config.scoring,
    )


class TestAllSixSyntheticJobsParseCleanly:
    """Section 18.1: "All 6 synthetic job descriptions parse without
    error." Each job's required/preferred/responsibility counts and
    minimum-years value are checked against a full hand-trace of
    SPECIFICATION.md Sections 10.2-10.6 against the real file content.
    """

    def test_job1_data_analyst_standard(self, app_config):
        profile = _parse("job_01_data_analyst_standard.txt", app_config)
        assert profile.confirmed is False
        assert profile.minimum_relevant_years == 2.0
        assert len(profile.responsibilities) == 5
        assert {r.canonical_name for r in profile.required_qualifications} == {
            "sql",
            "microsoft excel",
            "bachelor in data analytics",
        }
        sql = next(
            r for r in profile.required_qualifications if r.canonical_name == "sql"
        )
        assert sql.importance == 3
        assert sql.required is True
        preferred_names = {r.canonical_name for r in profile.preferred_qualifications}
        assert {"power bi", "python", "tableau"} <= preferred_names

    def test_job2_data_analyst_altheadings_no_preferred_section(self, app_config):
        profile = _parse("job_02_data_analyst_altheadings.txt", app_config)
        assert profile.minimum_relevant_years == 3.0
        assert profile.preferred_qualifications == []  # no preferred section at all
        assert len(profile.responsibilities) == 4
        assert {r.canonical_name for r in profile.required_qualifications} == {
            "sql",
            "microsoft excel",
            "bachelor in statistics",
        }

    def test_job3_data_engineer(self, app_config):
        profile = _parse("job_03_data_engineer.txt", app_config)
        assert profile.minimum_relevant_years == 3.0
        assert len(profile.responsibilities) == 5
        required_names = {r.canonical_name for r in profile.required_qualifications}
        assert {
            "sql",
            "python",
            "etl",
            "bachelor in computer science",
        } == required_names
        preferred_names = {r.canonical_name for r in profile.preferred_qualifications}
        assert {"apache airflow", "aws", "docker"} <= preferred_names

    def test_job4_bi_analyst_no_experience_minimum(self, app_config):
        profile = _parse("job_04_bi_analyst.txt", app_config)
        assert (
            profile.minimum_relevant_years is None
        )  # no experience minimum stated at all
        assert len(profile.responsibilities) == 4
        required_names = {r.canonical_name for r in profile.required_qualifications}
        assert {"power bi", "sql", "microsoft excel", "bachelor"} == required_names

    def test_job5_data_scientist_degree_or_equivalent(self, app_config):
        profile = _parse("job_05_data_scientist.txt", app_config)
        assert profile.minimum_relevant_years == 2.0
        edu = next(r for r in profile.required_qualifications if r.type == "education")
        assert edu.degree_level == "master"
        assert edu.field_of_study == "statistics"
        assert edu.allows_equivalent_experience is True
        assert edu.equivalent_years == 4.0
        assert edu.importance == 3  # the whole clause ends in "...is required"

    def test_job6_software_engineer_pmp_preferred(self, app_config):
        profile = _parse("job_06_software_engineer.txt", app_config)
        assert profile.minimum_relevant_years == 2.0
        cert_items = [
            r for r in profile.preferred_qualifications if r.type == "certification"
        ]
        assert len(cert_items) == 1
        assert cert_items[0].canonical_name == "pmp"
        assert cert_items[0].required is False

    def test_all_six_jobs_have_no_ambiguous_classification_warnings(self, app_config):
        """Every job has clear headings and unambiguous wording, so
        none should trigger AMBIGUOUS_REQUIREMENT_CLASSIFICATION or
        NO_HEADINGS."""
        for path in sorted(SAMPLE_JOBS_DIR.glob("*.txt")):
            profile = _parse(path.name, app_config)
            codes = {w.code for w in profile.warnings}
            assert codes == set(), f"{path.name} had unexpected warnings: {codes}"

    def test_responsibilities_have_sequential_positions_and_no_duplicates(
        self, app_config
    ):
        for path in sorted(SAMPLE_JOBS_DIR.glob("*.txt")):
            profile = _parse(path.name, app_config)
            positions = [r.position for r in profile.responsibilities]
            assert positions == list(range(len(profile.responsibilities))), path.name
            texts = [r.original_text for r in profile.responsibilities]
            assert len(texts) == len(
                set(texts)
            ), f"{path.name} had duplicate responsibilities"

    def test_every_requirement_confidence_in_valid_range(self, app_config):
        for path in sorted(SAMPLE_JOBS_DIR.glob("*.txt")):
            profile = _parse(path.name, app_config)
            for req in (
                profile.required_qualifications + profile.preferred_qualifications
            ):
                assert 0.0 <= req.confidence <= 1.0
                assert req.importance in (1, 2, 3)

    def test_title_is_passed_through_untouched(self, app_config):
        profile = _parse(
            "job_01_data_analyst_standard.txt", app_config, title="Senior Data Analyst"
        )
        assert profile.title == "Senior Data Analyst"


class TestSection10_1Validation:
    def test_empty_description_rejected(self, app_config):
        with pytest.raises(ValidationError):
            parse_job_description(
                "",
                title=None,
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )

    def test_too_short_description_rejected(self, app_config):
        with pytest.raises(ValidationError):
            parse_job_description(
                "Too short.",
                title=None,
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )

    def test_too_long_description_rejected(self, app_config):
        with pytest.raises(ValidationError):
            parse_job_description(
                "x" * 50001,
                title=None,
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )

    def test_nothing_scoreable_rejected_when_only_excluded_sections_present(
        self, app_config
    ):
        text = (
            "Company Name\n\n"
            "About Us\n"
            "We are a great company that does great things for great people every single day here.\n\n"
            "Benefits\n"
            "Health insurance, dental, vision, 401k matching, unlimited PTO, and a great culture await you.\n"
        )
        with pytest.raises(ValidationError, match="Nothing scoreable"):
            parse_job_description(
                text,
                title=None,
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )

    def test_degenerate_no_heading_garbage_rejected(self, app_config):
        with pytest.raises(ValidationError, match="Nothing scoreable"):
            parse_job_description(
                "x" * 150,
                title=None,
                taxonomy=app_config.taxonomy,
                scoring_config=app_config.scoring,
            )

    def test_benefits_text_yields_no_qualifications(self, app_config):
        """Section 18.1 fixture: benefits text yields no qualifications."""
        text = (
            "Data Analyst\n\n"
            "Requirements\n"
            "- Must have SQL.\n\n"
            "Benefits\n"
            "Health insurance, 401k matching, and unlimited PTO for all full-time employees here.\n"
        )
        profile = parse_job_description(
            text,
            title=None,
            taxonomy=app_config.taxonomy,
            scoring_config=app_config.scoring,
        )
        names = {
            r.canonical_name
            for r in profile.required_qualifications + profile.preferred_qualifications
        }
        assert names == {"sql"}


class TestNoHeadingsFallback:
    def test_no_headings_document_still_extracts_requirements_and_responsibilities(
        self, app_config
    ):
        text = (
            "We need someone who must have strong SQL skills for this role. "
            "Python is a plus for this position. "
            "You will build dashboards and write reports for the team every week. "
            "Our company offers great benefits and a 401k match program for employees."
        ) * 2
        profile = parse_job_description(
            text,
            title=None,
            taxonomy=app_config.taxonomy,
            scoring_config=app_config.scoring,
        )
        assert any(w.code == "NO_HEADINGS" for w in profile.warnings)
        required_names = {r.canonical_name for r in profile.required_qualifications}
        assert "sql" in required_names
        preferred_names = {r.canonical_name for r in profile.preferred_qualifications}
        assert "python" in preferred_names
        assert len(profile.responsibilities) >= 1
