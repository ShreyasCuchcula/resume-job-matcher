"""Integration tests for services/candidate_service.py against the full
sample_data/synthetic_resumes batch (SPECIFICATION.md Section 18.2,
Section 16, Section 8.1, Section 14.3).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.orm import Session

from db.models import Candidate, Resume
from services.candidate_service import (
    IngestionResult,
    UploadedFile,
    ingest_resume_batch,
)

EXPECTED_STATUS = {
    "job1_strong_match_analyst.pdf": "accepted",
    "job1_strong_match_analyst_duplicate.pdf": "duplicate",
    "job1_good_gaps_analyst.docx": "accepted",
    "job1_keyword_stuffer_analyst.pdf": "accepted",
    "job1_career_changer_analyst.docx": "accepted",
    "job1_missing_preferred_skill_analyst.pdf": "accepted",
    "job2_strong_match_analyst2.pdf": "accepted",
    "job2_good_gaps_analyst2.docx": "accepted",
    "job3_strong_match_engineer.pdf": "accepted",
    "job3_good_gaps_engineer_table.docx": "accepted",
    "job3_no_headings_engineer.pdf": "accepted",
    "job3_missing_dates_engineer.docx": "accepted",
    "job3_year_only_dates_engineer.pdf": "accepted",
    "job4_strong_match_bi.docx": "accepted",
    "job4_good_gaps_bi.pdf": "accepted",
    "job5_strong_match_scientist.docx": "accepted",
    "job5_degree_or_equivalent_scientist.pdf": "accepted",
    "job5_good_gaps_scientist.pdf": "accepted",
    "job5_weak_scientist.docx": "accepted",
    "job6_strong_match_swe.docx": "accepted",
    "job6_pmp_candidate_engineer.pdf": "accepted",
    "edge_corrupt_file.pdf": "corrupt",
    "edge_password_protected.pdf": "corrupt",
    "edge_probable_scan.pdf": "probable_scan",
    "edge_renamed_txt_as_pdf.pdf": "unsupported",
    "edge_unsupported_filetype.doc": "unsupported",
}


def _load_all(sample_resumes_dir: Path) -> list[UploadedFile]:
    return [
        UploadedFile(filename=p.name, content=p.read_bytes())
        for p in sorted(sample_resumes_dir.iterdir())
    ]


def _run_batch(
    db_session: Session, sample_resumes_dir: Path, upload_dir: Path
) -> list[IngestionResult]:
    files = _load_all(sample_resumes_dir)
    assert len(files) == 26
    return ingest_resume_batch(db_session, files, upload_dir=upload_dir)


class TestFullSyntheticBatch:
    """Section 18.2: full path through ingestion with a mixed batch;
    Section 16's acceptance table for every file-level edge case."""

    def test_all_26_files_get_the_expected_status(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        assert len(results) == 26

        by_filename = {r.original_filename: r for r in results}
        mismatches = [
            (name, expected, by_filename[name].status)
            for name, expected in EXPECTED_STATUS.items()
            if by_filename[name].status != expected
        ]
        assert not mismatches, f"status mismatches: {mismatches}"

    def test_one_corrupt_file_does_not_block_the_rest(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        statuses = {r.status for r in results}
        # corrupt files are present alongside a majority of accepted files -
        # the batch as a whole still completed and reported every file.
        assert "corrupt" in statuses
        assert sum(1 for r in results if r.status == "accepted") == 20

    def test_duplicate_detection_identifies_byte_identical_files(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        by_filename = {r.original_filename: r for r in results}

        original = by_filename["job1_strong_match_analyst.pdf"]
        duplicate = by_filename["job1_strong_match_analyst_duplicate.pdf"]
        assert original.status == "accepted"
        assert duplicate.status == "duplicate"
        assert original.sha256 == duplicate.sha256
        # no second candidate created for the duplicate
        assert duplicate.candidate_id is None

    def test_password_protected_pdf_reports_corrupt_without_crashing(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        by_filename = {r.original_filename: r for r in results}
        result = by_filename["edge_password_protected.pdf"]
        assert result.status == "corrupt"
        assert result.code == "PASSWORD_PROTECTED"
        assert "password" in result.message.lower()

    def test_probable_scan_pdf_rejected(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        by_filename = {r.original_filename: r for r in results}
        result = by_filename["edge_probable_scan.pdf"]
        assert result.status == "probable_scan"

    def test_renamed_txt_fails_signature_check(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        by_filename = {r.original_filename: r for r in results}
        result = by_filename["edge_renamed_txt_as_pdf.pdf"]
        assert result.status == "unsupported"
        assert result.code == "SIGNATURE_MISMATCH"

    def test_unsupported_extension_rejected(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        by_filename = {r.original_filename: r for r in results}
        result = by_filename["edge_unsupported_filetype.doc"]
        assert result.status == "unsupported"
        assert result.code == "UNSUPPORTED_EXTENSION"

    def test_display_identifiers_assigned_by_ascending_sha256(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        accepted = [r for r in results if r.status == "accepted"]
        by_hash_order = sorted(accepted, key=lambda r: r.sha256)
        expected_ids = [f"Candidate {i:03d}" for i in range(1, len(by_hash_order) + 1)]
        assert [r.display_identifier for r in by_hash_order] == expected_ids

    def test_accepted_files_written_to_disk_with_content_addressed_names(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        results = _run_batch(db_session, sample_resumes_dir, upload_dir)
        accepted = [r for r in results if r.status == "accepted"]

        disk_names = sorted(p.name for p in upload_dir.iterdir())
        expected_names = sorted(
            f"{r.sha256}.{Path(r.original_filename).suffix.lstrip('.')}"
            for r in accepted
        )
        assert disk_names == expected_names

    def test_db_rows_created_only_for_accepted_files(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        _run_batch(db_session, sample_resumes_dir, upload_dir)
        assert db_session.query(Candidate).count() == 20
        assert db_session.query(Resume).count() == 20

    def test_reuploading_the_same_batch_marks_everything_duplicate(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        first = _run_batch(db_session, sample_resumes_dir, upload_dir)
        assert sum(1 for r in first if r.status == "accepted") == 20

        second = _run_batch(db_session, sample_resumes_dir, upload_dir)
        # the 20 previously-accepted plus the 1 previously-duplicate file
        # are now all duplicates against what's in the DB; the corrupt/
        # probable_scan/unsupported files are re-evaluated the same way
        # each time since their content never changes.
        assert sum(1 for r in second if r.status == "duplicate") == 21
        assert db_session.query(Candidate).count() == 20  # no new rows


class TestTransactionalRollback:
    """Section 6.2 / 14.2: a DB failure mid-batch rolls back everything
    the batch would have written, leaving no partial rows."""

    def test_db_failure_rolls_back_whole_batch_and_reports_failed(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        files = [
            UploadedFile(
                filename="job1_strong_match_analyst.pdf",
                content=(
                    sample_resumes_dir / "job1_strong_match_analyst.pdf"
                ).read_bytes(),
            ),
            UploadedFile(
                filename="job2_strong_match_analyst2.pdf",
                content=(
                    sample_resumes_dir / "job2_strong_match_analyst2.pdf"
                ).read_bytes(),
            ),
            UploadedFile(
                filename="edge_corrupt_file.pdf",
                content=(sample_resumes_dir / "edge_corrupt_file.pdf").read_bytes(),
            ),
        ]

        def failing_commit(self):
            raise RuntimeError("simulated database outage")

        with patch.object(Session, "commit", failing_commit):
            results = ingest_resume_batch(db_session, files, upload_dir=upload_dir)

        by_filename = {r.original_filename: r for r in results}
        assert by_filename["job1_strong_match_analyst.pdf"].status == "failed"
        assert by_filename["job1_strong_match_analyst.pdf"].code == "DB_WRITE_FAILED"
        assert by_filename["job2_strong_match_analyst2.pdf"].status == "failed"
        # a file that was already going to be rejected is unaffected by the DB outage
        assert by_filename["edge_corrupt_file.pdf"].status == "corrupt"

        assert db_session.query(Candidate).count() == 0
        assert db_session.query(Resume).count() == 0
        assert list(upload_dir.iterdir()) == []


class TestOneBadFileNeverBlocksTheRest:
    def test_unexpected_exception_in_one_file_still_yields_full_batch_report(
        self, db_session, sample_resumes_dir, upload_dir
    ):
        good = UploadedFile(
            filename="job1_strong_match_analyst.pdf",
            content=(sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes(),
        )
        # A file whose "extension" claims .pdf but whose bytes are garbage
        # should be rejected cleanly rather than raising out of the batch.
        bad = UploadedFile(filename="broken.pdf", content=b"not a real pdf")

        results = ingest_resume_batch(db_session, [good, bad], upload_dir=upload_dir)

        assert len(results) == 2
        by_filename = {r.original_filename: r for r in results}
        assert by_filename["job1_strong_match_analyst.pdf"].status == "accepted"
        assert by_filename["broken.pdf"].status == "unsupported"
