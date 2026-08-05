"""Unit tests for ingestion/pdf_reader.py (SPECIFICATION.md Section 8.2)."""

from __future__ import annotations

import pytest

from domain.exceptions import CorruptFileError
from ingestion.pdf_reader import extract_pdf_text, pdf_needs_password


def test_extract_pdf_text_returns_readable_content(sample_resumes_dir):
    file_bytes = (sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes()
    text = extract_pdf_text(file_bytes)
    assert "SUMMARY" in text
    assert "PROFESSIONAL EXPERIENCE" in text
    assert len(text) > 200


def test_extract_pdf_text_raises_on_corrupt_file(sample_resumes_dir):
    file_bytes = (sample_resumes_dir / "edge_corrupt_file.pdf").read_bytes()
    with pytest.raises(CorruptFileError):
        extract_pdf_text(file_bytes)


def test_extract_pdf_text_raises_password_protected_message(sample_resumes_dir):
    file_bytes = (sample_resumes_dir / "edge_password_protected.pdf").read_bytes()
    with pytest.raises(CorruptFileError, match="password-protected"):
        extract_pdf_text(file_bytes)


def test_pdf_needs_password_detects_encrypted_file(sample_resumes_dir):
    encrypted = (sample_resumes_dir / "edge_password_protected.pdf").read_bytes()
    assert pdf_needs_password(encrypted) is True


def test_pdf_needs_password_false_for_normal_file(sample_resumes_dir):
    normal = (sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes()
    assert pdf_needs_password(normal) is False


def test_pdf_needs_password_false_for_garbage_bytes():
    assert pdf_needs_password(b"not a pdf") is False


def test_extract_pdf_text_near_empty_scan_extracts_short_text(sample_resumes_dir):
    file_bytes = (sample_resumes_dir / "edge_probable_scan.pdf").read_bytes()
    text = extract_pdf_text(file_bytes)
    assert len(text.strip()) < 200
