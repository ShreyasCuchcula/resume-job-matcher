"""Unit tests for ingestion/hashing.py (SPECIFICATION.md Section 8.1
step 4, Section 14.3)."""

from __future__ import annotations

import hashlib

from ingestion.hashing import is_duplicate, sha256_hex, stored_filename


def test_sha256_hex_matches_stdlib():
    data = b"some resume bytes"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()


def test_sha256_hex_is_deterministic():
    data = b"identical content"
    assert sha256_hex(data) == sha256_hex(data)


def test_sha256_hex_differs_for_different_content():
    assert sha256_hex(b"content a") != sha256_hex(b"content b")


def test_stored_filename_format():
    digest = "a" * 64
    assert stored_filename(digest, "pdf") == f"{digest}.pdf"
    assert stored_filename(digest, ".DOCX") == f"{digest}.docx"


def test_is_duplicate():
    known = {"abc123", "def456"}
    assert is_duplicate("abc123", known)
    assert not is_duplicate("zzz999", known)
    assert not is_duplicate("abc123", set())


def test_identical_files_hash_identically(sample_resumes_dir):
    original = (sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes()
    duplicate = (
        sample_resumes_dir / "job1_strong_match_analyst_duplicate.pdf"
    ).read_bytes()
    assert sha256_hex(original) == sha256_hex(duplicate)


def test_different_resumes_hash_differently(sample_resumes_dir):
    a = (sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes()
    b = (sample_resumes_dir / "job2_strong_match_analyst2.pdf").read_bytes()
    assert sha256_hex(a) != sha256_hex(b)
