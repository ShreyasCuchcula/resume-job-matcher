"""Stage 8 full-pipeline integration tests: every scoring component
combined into a final score, ranked, against real job descriptions
and real synthetic resumes (SPECIFICATION.md Section 18.1/18.3).
Complements tests/integration/test_scoring_service.py (which exercises
DB persistence) by exercising matching.scoring_engine.score_candidate
+ rank_match_results directly, in memory, across the whole sample set.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest

from config.settings import get_app_config
from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from matching.responsibility_scorer import build_vectorizer
from matching.scoring_engine import ScoringContext, rank_match_results, score_candidate
from parsing.job_parser import confirm_job_profile, parse_job_description
from parsing.resume_parser import build_resume_extractor_context, parse_resume

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

JOB_TITLES = {
    "job_01_data_analyst_standard.txt": "Data Analyst",
    "job_02_data_analyst_altheadings.txt": "Data Analyst II",
    "job_03_data_engineer.txt": "Data Engineer",
    "job_04_bi_analyst.txt": "BI Analyst",
    "job_05_data_scientist.txt": "Data Scientist",
    "job_06_software_engineer.txt": "Software Engineer",
}

DEFAULT_WEIGHTS = {
    "required": 0.45,
    "experience": 0.20,
    "responsibility": 0.20,
    "preferred": 0.15,
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


def _parse_resume(
    filename: str, resume_context, *, display_identifier: str | None = None
):
    text = _extract_text(RESUMES_DIR / filename)
    return parse_resume(
        text,
        file_hash="x" * 64,
        display_identifier=display_identifier or filename,
        context=resume_context,
        run_date=RUN_DATE,
    )


def _all_resume_files() -> list[str]:
    return sorted(
        p.name for p in RESUMES_DIR.iterdir() if p.name not in NON_RESUME_FILES
    )


def _context_for(job, candidates, app_config) -> ScoringContext:
    corpus = [r.normalized_text for r in job.responsibilities]
    for candidate in candidates:
        corpus.extend(b.normalized_text for b in candidate.evidence_bullets)
    vectorizer = build_vectorizer().fit(corpus) if corpus else None
    return ScoringContext(
        run_id=uuid4(),
        scoring_version=app_config.scoring.scoring_version,
        taxonomy=app_config.taxonomy,
        vectorizer=vectorizer,
        run_date=RUN_DATE,
        default_weights=DEFAULT_WEIGHTS,
        minimum_similarity=app_config.scoring.responsibility_matching.minimum_similarity,
        role_relevance_threshold=app_config.scoring.responsibility_matching.role_relevance_threshold,
    )


class TestSmokeAllJobsAgainstAllResumes:
    """Every real job scored against every real parseable resume via
    the full score_candidate() pipeline - no crashes, every final
    score in [0, 100], weights always sum to 1.0."""

    @pytest.mark.parametrize("job_filename", sorted(JOB_TITLES))
    def test_full_pipeline_scores_without_raising(
        self, job_filename, app_config, resume_context
    ):
        job = _parse_and_confirm_job(job_filename, app_config)
        resume_files = _all_resume_files()
        candidates = [_parse_resume(f, resume_context) for f in resume_files]
        context = _context_for(job, candidates, app_config)

        for candidate in candidates:
            result = score_candidate(job, candidate, context)
            assert 0.0 <= result.final_score <= 100.0
            assert abs(sum(result.applied_weights.values()) - 1.0) < 1e-9


class TestJob1RankingMatchesGroundTruth:
    """expected_rankings.md Section 2: Jordan Ellis > Dakota Reyes >
    Morgan Patel > Casey Nguyen > Riley Thompson."""

    def test_ranking_order(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_01_data_analyst_standard.txt", app_config)
        files = {
            "Jordan Ellis": "job1_strong_match_analyst.pdf",
            "Dakota Reyes": "job1_missing_preferred_skill_analyst.pdf",
            "Morgan Patel": "job1_good_gaps_analyst.docx",
            "Casey Nguyen": "job1_keyword_stuffer_analyst.pdf",
            "Riley Thompson": "job1_career_changer_analyst.docx",
        }
        candidates = {
            name: _parse_resume(f, resume_context, display_identifier=name)
            for name, f in files.items()
        }
        context = _context_for(job, list(candidates.values()), app_config)
        results = [score_candidate(job, c, context) for c in candidates.values()]
        display_identifiers = {
            r.candidate_id: c.display_identifier
            for r, c in zip(results, candidates.values())
        }

        ranked = rank_match_results(results, display_identifiers)
        ranked_names = [display_identifiers[r.candidate_id] for r in ranked]

        assert ranked_names == [
            "Jordan Ellis",
            "Dakota Reyes",
            "Morgan Patel",
            "Casey Nguyen",
            "Riley Thompson",
        ]


class TestJob2PreferredAbsentRedistribution:
    def test_applied_weights_exclude_preferred(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_02_data_analyst_altheadings.txt", app_config)
        assert job.preferred_qualifications == []
        candidate = _parse_resume("job2_strong_match_analyst2.pdf", resume_context)
        context = _context_for(job, [candidate], app_config)
        result = score_candidate(job, candidate, context)
        assert "preferred" not in result.applied_weights
        assert result.preferred_score is None
        assert abs(sum(result.applied_weights.values()) - 1.0) < 1e-9


class TestJob4ExperienceAbsentRedistribution:
    def test_applied_weights_exclude_experience(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_04_bi_analyst.txt", app_config)
        assert job.minimum_relevant_years is None
        candidate = _parse_resume("job4_strong_match_bi.docx", resume_context)
        context = _context_for(job, [candidate], app_config)
        result = score_candidate(job, candidate, context)
        assert "experience" not in result.applied_weights
        assert result.experience_score is None
        assert abs(sum(result.applied_weights.values()) - 1.0) < 1e-9


class TestNameSwapInvariantOnFinalScore:
    """Section 9.4's acceptance test, carried all the way through to
    the final weighted score: changing only the candidate's name/email
    must yield a bit-identical final_score and identical component
    scores, since nothing PII-derived is ever an input to scoring."""

    def test_final_score_identical_after_name_swap(self, app_config, resume_context):
        job = _parse_and_confirm_job("job_01_data_analyst_standard.txt", app_config)

        original_text = _extract_text(RESUMES_DIR / "job1_strong_match_analyst.pdf")
        swapped_text = original_text.replace("Jordan Ellis", "Alex Rivera").replace(
            "jordan.ellis", "alex.rivera"
        )

        original = parse_resume(
            original_text,
            file_hash="x" * 64,
            display_identifier="Candidate 001",
            context=resume_context,
            run_date=RUN_DATE,
        )
        swapped = parse_resume(
            swapped_text,
            file_hash="y" * 64,
            display_identifier="Candidate 001",
            context=resume_context,
            run_date=RUN_DATE,
        )

        context = _context_for(job, [original, swapped], app_config)
        result_original = score_candidate(job, original, context)
        result_swapped = score_candidate(job, swapped, context)

        assert result_original.final_score == result_swapped.final_score
        assert result_original.required_score == result_swapped.required_score
        assert result_original.experience_score == result_swapped.experience_score
        assert (
            result_original.responsibility_score == result_swapped.responsibility_score
        )
        assert result_original.preferred_score == result_swapped.preferred_score
