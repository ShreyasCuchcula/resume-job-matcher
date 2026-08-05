"""Integration tests for matching/experience_scorer.py against real job
descriptions and real synthetic resumes (SPECIFICATION.md Section
18.1/18.3), including the acceptance scenarios expected_rankings.md
documents by name.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from config.settings import get_app_config
from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from parsing.job_parser import confirm_job_profile, parse_job_description
from parsing.resume_parser import build_resume_extractor_context, parse_resume
from matching.scoring_engine import compute_relevant_years, score_experience

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JOBS_DIR = REPO_ROOT / "sample_data" / "jobs"
RESUMES_DIR = REPO_ROOT / "sample_data" / "synthetic_resumes"
RUN_DATE = date(2026, 8, 1)

NON_RESUME_FILES = {
    "edge_corrupt_file.pdf",
    "edge_password_protected.pdf",
    "edge_probable_scan.pdf",
    "edge_renamed_txt_as_pdf.pdf",
    "edge_unsupported_filetype.doc",
}

# The job's own displayed title (Page 1's optional title field, per
# Section 15.2) - the synthetic .txt fixtures each open with exactly
# this line, matching a titles.json canonical entry.
JOB_TITLES = {
    "job_01_data_analyst_standard.txt": "Data Analyst",
    "job_02_data_analyst_altheadings.txt": "Data Analyst II",
    "job_03_data_engineer.txt": "Data Engineer",
    "job_04_bi_analyst.txt": "BI Analyst",
    "job_05_data_scientist.txt": "Data Scientist",
    "job_06_software_engineer.txt": "Software Engineer",
}


@pytest.fixture(scope="module")
def app_config():
    return get_app_config()


@pytest.fixture(scope="module")
def resume_context(app_config):
    return build_resume_extractor_context(app_config.taxonomy)


def _extract_text(path: Path) -> str:
    data = path.read_bytes()
    return extract_pdf_text(data) if path.suffix == ".pdf" else extract_docx_text(data)


def _parse_and_confirm_job(filename: str, app_config):
    text = (JOBS_DIR / filename).read_text(encoding="utf-8")
    profile = parse_job_description(
        text,
        title=JOB_TITLES[filename],
        taxonomy=app_config.taxonomy,
        scoring_config=app_config.scoring,
    )
    return confirm_job_profile(profile)


def _parse_resume(filename: str, resume_context):
    text = _extract_text(RESUMES_DIR / filename)
    return parse_resume(
        text,
        file_hash="x" * 64,
        display_identifier=filename,
        context=resume_context,
        run_date=RUN_DATE,
    )


def _all_resume_files() -> list[str]:
    return sorted(
        p.name for p in RESUMES_DIR.iterdir() if p.name not in NON_RESUME_FILES
    )


class TestSmokeAllJobsAgainstAllResumes:
    @pytest.mark.parametrize("job_filename", sorted(JOB_TITLES))
    def test_experience_scores_without_raising(
        self, job_filename, app_config, resume_context
    ):
        job = _parse_and_confirm_job(job_filename, app_config)
        for resume_filename in _all_resume_files():
            candidate = _parse_resume(resume_filename, resume_context)
            result = score_experience(
                job, candidate, app_config.taxonomy, run_date=RUN_DATE
            )
            if result.score is not None:
                assert 0.0 <= result.score <= 100.0
            years = compute_relevant_years(
                job, candidate, app_config.taxonomy, run_date=RUN_DATE
            )
            assert years >= 0.0


class TestPeytonMarshYearOnlyDates:
    """expected_rankings.md acceptance scenario 7: "2019 - 2022"
    resolves to ~4.0 years internally (Jan 1 - Dec 31), clearing the
    3-year minimum, with lowered date_confidence surfaced on the
    evidence rather than discounting the score itself."""

    def test_year_only_dates_clear_the_minimum(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_03_data_engineer.txt", app_config)
        candidate = _parse_resume("job3_year_only_dates_engineer.pdf", resume_context)
        result = score_experience(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert result.score == 100.00
        assert result.evidence
        assert result.evidence[0].raw_strength == 0.6


class TestSkylerVanceMissingDates:
    """expected_rankings.md: the single employment entry has no dates
    at all, so it's excluded entirely from the experience-years
    calculation - 0 relevant years against the 3-year minimum, with a
    MISSING_DATES warning explicitly saying experience may be
    underestimated."""

    def test_missing_dates_yield_zero_with_warning(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_03_data_engineer.txt", app_config)
        candidate = _parse_resume("job3_missing_dates_engineer.docx", resume_context)
        result = score_experience(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert result.score == 0.00
        assert any(w.code == "MISSING_DATES" for w in result.warnings)


class TestElliotMarshRoleRelevance:
    """expected_rankings.md: a reporting-analyst role doesn't clear the
    role-relevance bar for "Data Scientist" - experience must drop to
    0.00, not merely be discounted, since none of the tenure counts as
    relevant at all."""

    def test_unrelated_title_yields_zero_relevant_years(
        self, app_config, resume_context
    ):
        job = _parse_and_confirm_job("job_05_data_scientist.txt", app_config)
        candidate = _parse_resume("job5_weak_scientist.docx", resume_context)
        result = score_experience(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert result.score == 0.00
        assert result.evidence == []


class TestHarperNakamuraRelevantYearsMatchesGroundTruth:
    """expected_rankings.md: "~7 years of directly relevant Data
    Scientist experience" - verifies compute_relevant_years produces
    that figure from the real resume (Jun 2019 - run date 2026-08-01
    under an exact "Data Scientist" title match), not a hand-supplied
    constant."""

    def test_computed_relevant_years_is_approximately_7(
        self, app_config, resume_context
    ):
        job = _parse_and_confirm_job("job_05_data_scientist.txt", app_config)
        candidate = _parse_resume(
            "job5_degree_or_equivalent_scientist.pdf", resume_context
        )
        years = compute_relevant_years(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert 6.5 <= years <= 7.5


class TestJob1StrongMatchClearsMinimum:
    """expected_rankings.md: Jordan Ellis has "2 roles totaling well
    over the 2-year minimum" -> Experience = 100.00."""

    def test_jordan_ellis_clears_the_minimum(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_01_data_analyst_standard.txt", app_config)
        candidate = _parse_resume("job1_strong_match_analyst.pdf", resume_context)
        result = score_experience(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert result.score == 100.00


class TestJob4NoExperienceMinimum:
    """expected_rankings.md: Job 4 (BI Analyst) states no experience
    minimum at all -> experience_score=None for every candidate."""

    @pytest.mark.parametrize(
        "resume_filename", ["job4_strong_match_bi.docx", "job4_good_gaps_bi.pdf"]
    )
    def test_experience_score_is_none(
        self, resume_filename, app_config, resume_context
    ):
        job = _parse_and_confirm_job("job_04_bi_analyst.txt", app_config)
        assert job.minimum_relevant_years is None
        candidate = _parse_resume(resume_filename, resume_context)
        result = score_experience(
            job, candidate, app_config.taxonomy, run_date=RUN_DATE
        )
        assert result.score is None
