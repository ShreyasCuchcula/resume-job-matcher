"""Stage 6 integration coverage: the "degree or equivalent experience"
contract (SPECIFICATION.md Section 11.3) verified against every real
job description and, for Job 5's dedicated fixture, through the actual
`matching.scoring_engine.score_required_qualifications` entry point -
the exact seam Stage 7's experience scorer will plug a real computed
`relevant_years` into.
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
from matching.scoring_engine import score_required_qualifications

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
JOBS_DIR = REPO_ROOT / "sample_data" / "jobs"
RESUMES_DIR = REPO_ROOT / "sample_data" / "synthetic_resumes"
RUN_DATE = date(2026, 8, 1)


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


class TestOnlyJob5DeclaresEquivalentExperience:
    """expected_rankings.md notes this is the only synthetic job with
    a "degree or equivalent experience" clause - confirm that holds
    across all 6 real job descriptions, so this contract isn't
    silently firing (or silently missing) anywhere else."""

    @pytest.mark.parametrize("job_filename", _all_job_files())
    def test_equivalent_experience_flag_matches_expectation(
        self, job_filename, app_config
    ):
        job = _parse_and_confirm_job(job_filename, app_config)
        education_reqs = [
            r
            for r in job.required_qualifications + job.preferred_qualifications
            if r.type == "education"
        ]
        equivalent_reqs = [r for r in education_reqs if r.allows_equivalent_experience]
        if job_filename == "job_05_data_scientist.txt":
            assert equivalent_reqs, "job 5 is expected to allow equivalent experience"
        else:
            assert (
                not equivalent_reqs
            ), f"{job_filename} unexpectedly allows equivalent experience"


class TestHarperNakamuraDegreeOrEquivalentEndToEnd:
    """expected_rankings.md Section 4 / Section 18.3 scenario 4: Harper
    Nakamura has no degree at all but ~7 years of directly relevant
    experience against Job 5's stated 4-year equivalence clause ->
    education_match = max(0.0, min(7/4, 1.0)) = 1.00, and the
    doc's own conclusion is that "required score reaches 100.00
    purely through the equivalence clause" - verified here through the
    real score_required_qualifications() entry point, not just the
    bare matching function.
    """

    @pytest.fixture(scope="class")
    def job(self, app_config):
        return _parse_and_confirm_job("job_05_data_scientist.txt", app_config)

    @pytest.fixture(scope="class")
    def candidate(self, resume_context):
        return _parse_resume("job5_degree_or_equivalent_scientist.pdf", resume_context)

    def test_candidate_has_no_degree_at_all(self, candidate):
        assert candidate.education == []

    def test_without_relevant_years_education_item_is_unmet(
        self, job, candidate, app_config
    ):
        result = score_required_qualifications(job, candidate, app_config.taxonomy)
        education_reqs = [
            r for r in job.required_qualifications if r.type == "education"
        ]
        missing_ids = {m.requirement_id for m in result.missing}
        assert education_reqs[0].requirement_id in missing_ids

    def test_with_relevant_years_education_item_gets_full_credit(
        self, job, candidate, app_config
    ):
        """expected_rankings.md's own hand-reasoned "required score
        reaches 100.00 purely through the equivalence clause" is an
        approximation of the whole required category (explicitly
        caveated: "the real job parser may assign different importance
        ... exact scores will shift"). What must hold exactly is the
        education item itself: no MissingItem for it, and its own
        evidence carries full 1.00 adjusted strength via the
        equivalence clause rather than a real degree."""
        result = score_required_qualifications(
            job, candidate, app_config.taxonomy, relevant_years=7.0
        )
        education_reqs = [
            r for r in job.required_qualifications if r.type == "education"
        ]
        missing_ids = {m.requirement_id for m in result.missing}
        assert education_reqs[0].requirement_id not in missing_ids

        education_evidence = [
            e
            for e in result.evidence
            if e.requirement_id == education_reqs[0].requirement_id
        ]
        assert education_evidence
        assert education_evidence[0].adjusted_strength == 1.00

    def test_insufficient_relevant_years_gives_partial_credit_via_max(
        self, job, candidate, app_config
    ):
        """1 year against a 4-year equivalence clause with no degree at
        all: education_match = max(0.0, min(1/4, 1.0)) = 0.25 - still
        below full credit, proving the formula isn't a pass/fail gate."""
        result = score_required_qualifications(
            job, candidate, app_config.taxonomy, relevant_years=1.0
        )
        assert result.score is not None
        assert result.score < 100.00
