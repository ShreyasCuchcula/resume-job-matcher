"""Integration tests for matching/qualification_matcher.py +
matching/scoring_engine.py against real job descriptions and real
synthetic resumes (SPECIFICATION.md Section 18.1/18.3)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from config.settings import get_app_config
from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from parsing.job_parser import confirm_job_profile, parse_job_description
from parsing.resume_parser import build_resume_extractor_context, parse_resume
from matching.qualification_matcher import match_qualifications
from matching.scoring_engine import (
    score_preferred_qualifications,
    score_required_qualifications,
)

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
        title=None,
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


def _all_job_files() -> list[str]:
    return sorted(p.name for p in JOBS_DIR.iterdir())


def _all_resume_files() -> list[str]:
    return sorted(
        p.name for p in RESUMES_DIR.iterdir() if p.name not in NON_RESUME_FILES
    )


class TestSmokeAllJobsAgainstAllResumes:
    """Section 18.1: "Test on all 6 job descriptions" / "All candidates
    from synthetic resumes" - every (job, resume) pair must score
    without raising, and every ComponentResult must be well-formed."""

    @pytest.mark.parametrize("job_filename", _all_job_files())
    def test_job_scores_against_every_resume_without_raising(
        self, job_filename, app_config, resume_context
    ):
        job = _parse_and_confirm_job(job_filename, app_config)
        for resume_filename in _all_resume_files():
            candidate = _parse_resume(resume_filename, resume_context)
            required = score_required_qualifications(
                job, candidate, app_config.taxonomy
            )
            preferred = score_preferred_qualifications(
                job, candidate, app_config.taxonomy
            )
            for result in (required, preferred):
                if result.score is not None:
                    assert 0.0 <= result.score <= 100.0
                for item in result.evidence:
                    assert item.evidence_text.strip()


class TestJob6PmpScenario:
    """expected_rankings.md Section 5: Reese Chandler holds PMP (full
    preferred credit); Finley Osei is a "PMP candidate" (not held,
    0.00 + PENDING_CREDENTIAL warning) - PMP is preferred, not
    required, on this job."""

    @pytest.fixture(scope="class")
    def job(self, app_config):
        return _parse_and_confirm_job("job_06_software_engineer.txt", app_config)

    def test_pmp_held_gets_full_preferred_credit(self, job, app_config, resume_context):
        candidate = _parse_resume("job6_strong_match_swe.docx", resume_context)
        result = score_preferred_qualifications(job, candidate, app_config.taxonomy)
        pmp_evidence = [e for e in result.evidence if e.matched_canonical == "pmp"]
        assert pmp_evidence, "expected PMP to be matched as held"
        assert pmp_evidence[0].adjusted_strength == 1.00

    def test_pmp_candidate_is_not_held_and_warns(self, job, app_config, resume_context):
        candidate = _parse_resume("job6_pmp_candidate_engineer.pdf", resume_context)
        result = score_preferred_qualifications(job, candidate, app_config.taxonomy)
        pmp_missing = [m for m in result.missing if m.canonical_name == "pmp"]
        assert pmp_missing
        assert pmp_missing[0].status == "pending_credential"
        assert any(w.code == "PENDING_CREDENTIAL" for w in result.warnings)


class TestJob5DegreeOrEquivalent:
    """expected_rankings.md Section 4 / Section 18.3 scenario 4: Harper
    Nakamura has no degree at all but the job allows "or equivalent
    experience of 4 years" - with relevant_years supplied (Stage 7
    will compute this for real), education credit reaches 1.00 via the
    equivalence clause rather than the (absent) degree."""

    @pytest.fixture(scope="class")
    def job(self, app_config):
        return _parse_and_confirm_job("job_05_data_scientist.txt", app_config)

    def test_equivalent_years_clause_parsed_from_job(self, job):
        education_reqs = [
            r for r in job.required_qualifications if r.type == "education"
        ]
        assert education_reqs
        req = education_reqs[0]
        assert req.allows_equivalent_experience is True
        assert req.equivalent_years == 4.0

    def test_no_degree_candidate_scores_zero_education_without_relevant_years(
        self, job, app_config, resume_context
    ):
        candidate = _parse_resume(
            "job5_degree_or_equivalent_scientist.pdf", resume_context
        )
        assert candidate.education == []
        result = score_required_qualifications(job, candidate, app_config.taxonomy)
        education_reqs = [
            r for r in job.required_qualifications if r.type == "education"
        ]
        missing_education = [
            m
            for m in result.missing
            if m.requirement_id == education_reqs[0].requirement_id
        ]
        assert missing_education

    def test_no_degree_candidate_scores_full_credit_with_relevant_years_supplied(
        self, job, app_config, resume_context
    ):
        candidate = _parse_resume(
            "job5_degree_or_equivalent_scientist.pdf", resume_context
        )
        education_reqs = [
            r for r in job.required_qualifications if r.type == "education"
        ]
        result = match_qualifications(
            education_reqs, candidate, app_config.taxonomy, relevant_years=7.0
        )
        assert result.score == 100.00


class TestJob2NoPreferredSection:
    """expected_rankings.md Section 5: Job 2 has no preferred section
    at all - both candidates should show preferred_score=None."""

    @pytest.fixture(scope="class")
    def job(self, app_config):
        return _parse_and_confirm_job("job_02_data_analyst_altheadings.txt", app_config)

    def test_no_preferred_qualifications_parsed(self, job):
        assert job.preferred_qualifications == []

    @pytest.mark.parametrize(
        "resume_filename",
        ["job2_strong_match_analyst2.pdf", "job2_good_gaps_analyst2.docx"],
    )
    def test_preferred_score_is_none_for_both_candidates(
        self, job, resume_filename, app_config, resume_context
    ):
        candidate = _parse_resume(resume_filename, resume_context)
        result = score_preferred_qualifications(job, candidate, app_config.taxonomy)
        assert result.score is None
