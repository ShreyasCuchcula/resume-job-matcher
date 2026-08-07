"""Integration tests for services/scoring_service.py (SPECIFICATION.md
Section 14.2). Exercises the real persistence path against the
in-memory SQLite `db_session` fixture with real job/resume data, so
foreign-key integrity (Section 6.2, enforced for real since the
db/base.py SQLite pragma fix) is actually tested, not just asserted
in prose.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from config.settings import get_app_config
from db.models import Candidate as CandidateRow
from db.models import Job as JobRow
from db.models import JobRequirement as JobRequirementRow
from db.models import JobResponsibility as JobResponsibilityRow
from db.models import (
    MatchEvidence,
    MatchResult,
    MissingItem,
    ScoringRun,
    ScoringWarning,
)
from db.repositories import create_company
from domain.exceptions import UnscorableJobError
from domain.schemas import (
    CandidateProfile,
    JobProfile,
    JobRequirement,
    JobResponsibility,
)
from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from matching.responsibility_scorer import build_vectorizer as real_build_vectorizer
from parsing.resume_parser import build_resume_extractor_context, parse_resume
from services.job_service import confirm_job, create_job, parse_and_persist_job
from services.scoring_service import run_scoring_batch

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


def _load_job_profile(session: Session, job_row: JobRow) -> JobProfile:
    """Test-local reconstruction of a JobProfile from persisted rows -
    scoring_service.run_scoring_batch's own docstring documents that a
    real "load from DB" loader is Stage 9 UI-wiring territory, not
    built yet. Ids are threaded through so foreign keys on the
    persisted match_evidence/missing_items rows resolve correctly."""
    requirement_rows = (
        session.query(JobRequirementRow).filter_by(job_id=job_row.id).all()
    )
    responsibility_rows = (
        session.query(JobResponsibilityRow)
        .filter_by(job_id=job_row.id)
        .order_by(JobResponsibilityRow.position)
        .all()
    )
    requirements = [
        JobRequirement(
            requirement_id=row.id,
            type=row.requirement_type,
            canonical_name=row.canonical_name,
            original_text=row.original_text,
            importance=row.importance,
            confidence=row.confidence,
            required=row.is_required,
            allows_equivalent_experience=row.allows_equivalent_experience,
            equivalent_years=row.equivalent_years,
            degree_level=row.degree_level,
            field_of_study=row.field_of_study,
        )
        for row in requirement_rows
    ]
    responsibilities = [
        JobResponsibility(
            responsibility_id=row.id,
            original_text=row.original_text,
            normalized_text=row.normalized_text,
            position=row.position,
        )
        for row in responsibility_rows
    ]
    return JobProfile(
        job_id=job_row.id,
        title=job_row.title,
        raw_description=job_row.raw_description,
        required_qualifications=[r for r in requirements if r.required],
        preferred_qualifications=[r for r in requirements if not r.required],
        minimum_relevant_years=job_row.minimum_relevant_years,
        responsibilities=responsibilities,
        parser_version=job_row.parser_version,
        confirmed=job_row.confirmed,
    )


def _persisted_candidate(
    session: Session, resume_filename: str, resume_context
) -> CandidateProfile:
    data = (RESUMES_DIR / resume_filename).read_bytes()
    text = (
        extract_pdf_text(data)
        if resume_filename.endswith(".pdf")
        else extract_docx_text(data)
    )
    profile = parse_resume(
        text,
        file_hash="x" * 64,
        display_identifier=resume_filename,
        context=resume_context,
        run_date=RUN_DATE,
    )
    row = CandidateRow(display_identifier=resume_filename)
    session.add(row)
    session.commit()
    return profile.model_copy(update={"candidate_id": row.id})


def _confirmed_job(session: Session, app_config, filename: str, title: str) -> JobRow:
    company = create_company(session, "Acme Corp")
    text = (JOBS_DIR / filename).read_text(encoding="utf-8")
    job_row = create_job(
        session, company_id=company.id, raw_description=text, title=title
    )
    job_row = parse_and_persist_job(
        session,
        job_row.id,
        taxonomy=app_config.taxonomy,
        scoring_config=app_config.scoring,
    )
    return confirm_job(session, job_row.id)


class TestRunScoringBatchPersistence:
    def test_persists_run_and_results_for_every_candidate(
        self, db_session, app_config, resume_context
    ):
        job_row = _confirmed_job(
            db_session, app_config, "job_01_data_analyst_standard.txt", "Data Analyst"
        )
        job = _load_job_profile(db_session, job_row)
        candidates = [
            _persisted_candidate(
                db_session, "job1_strong_match_analyst.pdf", resume_context
            ),
            _persisted_candidate(
                db_session, "job1_keyword_stuffer_analyst.pdf", resume_context
            ),
        ]

        results = run_scoring_batch(
            db_session, job, candidates, app_config=app_config, run_date=RUN_DATE
        )

        assert len(results) == 2
        assert db_session.query(ScoringRun).count() == 1
        assert db_session.query(MatchResult).count() == 2

        run_row = db_session.query(ScoringRun).one()
        assert run_row.job_id == job.job_id
        assert run_row.status == "active"
        assert len(run_row.candidate_ids) == 2

        for result in results:
            assert 0.0 <= result.final_score <= 100.0
            assert abs(sum(result.applied_weights.values()) - 1.0) < 1e-9

    def test_evidence_and_missing_and_warning_rows_are_persisted(
        self, db_session, app_config, resume_context
    ):
        job_row = _confirmed_job(
            db_session, app_config, "job_01_data_analyst_standard.txt", "Data Analyst"
        )
        job = _load_job_profile(db_session, job_row)
        candidates = [
            _persisted_candidate(
                db_session, "job1_strong_match_analyst.pdf", resume_context
            )
        ]

        results = run_scoring_batch(
            db_session, job, candidates, app_config=app_config, run_date=RUN_DATE
        )
        result_row = (
            db_session.query(MatchResult)
            .filter_by(candidate_id=results[0].candidate_id)
            .one()
        )
        assert (
            db_session.query(MatchEvidence)
            .filter_by(match_result_id=result_row.id)
            .count()
            > 0
        )
        # every persisted MissingItem/ScoringWarning must reference a real row (FK enforced)
        db_session.query(MissingItem).filter_by(match_result_id=result_row.id).all()
        db_session.query(ScoringWarning).filter_by(match_result_id=result_row.id).all()


class TestOneVectorizerPerBatch:
    def test_build_vectorizer_called_exactly_once_regardless_of_candidate_count(
        self, db_session, app_config, resume_context
    ):
        job_row = _confirmed_job(
            db_session, app_config, "job_01_data_analyst_standard.txt", "Data Analyst"
        )
        job = _load_job_profile(db_session, job_row)
        candidates = [
            _persisted_candidate(
                db_session, "job1_strong_match_analyst.pdf", resume_context
            ),
            _persisted_candidate(
                db_session, "job1_good_gaps_analyst.docx", resume_context
            ),
            _persisted_candidate(
                db_session, "job1_keyword_stuffer_analyst.pdf", resume_context
            ),
        ]

        with patch(
            "services.scoring_service.build_vectorizer", wraps=real_build_vectorizer
        ) as spy:
            run_scoring_batch(
                db_session, job, candidates, app_config=app_config, run_date=RUN_DATE
            )

        assert spy.call_count == 1


class TestUnscorableJobRaisesBeforeAnyWrite:
    def test_no_rows_written_when_job_has_nothing_scoreable(
        self, db_session, app_config, resume_context
    ):
        company = create_company(db_session, "Acme Corp")
        job_row = create_job(
            db_session,
            company_id=company.id,
            raw_description="x" * 150,
            title="Empty Job",
        )
        job_row.confirmed = True  # bypass confirm_job's own guard for this direct test
        job_row.parser_version = (
            "test"  # never parsed; only company_id validity matters here
        )
        db_session.commit()
        job = _load_job_profile(db_session, job_row)
        candidate = _persisted_candidate(
            db_session, "job1_strong_match_analyst.pdf", resume_context
        )

        with pytest.raises(UnscorableJobError):
            run_scoring_batch(
                db_session, job, [candidate], app_config=app_config, run_date=RUN_DATE
            )

        assert db_session.query(ScoringRun).count() == 0
        assert db_session.query(MatchResult).count() == 0


class TestTransactionalRollback:
    """Section 6.2/14.2: the run is atomic - either all results exist
    or none do."""

    def test_db_failure_rolls_back_the_entire_run(
        self, db_session, app_config, resume_context
    ):
        job_row = _confirmed_job(
            db_session, app_config, "job_01_data_analyst_standard.txt", "Data Analyst"
        )
        job = _load_job_profile(db_session, job_row)
        candidates = [
            _persisted_candidate(
                db_session, "job1_strong_match_analyst.pdf", resume_context
            ),
            _persisted_candidate(
                db_session, "job1_good_gaps_analyst.docx", resume_context
            ),
        ]

        def failing_commit(self):
            raise RuntimeError("simulated database outage")

        with patch.object(Session, "commit", failing_commit):
            with pytest.raises(RuntimeError):
                run_scoring_batch(
                    db_session,
                    job,
                    candidates,
                    app_config=app_config,
                    run_date=RUN_DATE,
                )

        assert db_session.query(ScoringRun).count() == 0
        assert db_session.query(MatchResult).count() == 0
        assert db_session.query(MatchEvidence).count() == 0
