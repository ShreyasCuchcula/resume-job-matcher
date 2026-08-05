"""Unit tests for ingestion/validation.py (SPECIFICATION.md Section 8.1
steps 1-3 and 6)."""

from __future__ import annotations

from ingestion.validation import (
    extension_of,
    has_allowed_extension,
    is_probable_scan,
    is_within_size_limit,
    matches_declared_signature,
    validate_before_extraction,
)


def test_extension_of_lowercases_and_strips_dot():
    assert extension_of("Resume.PDF") == "pdf"
    assert extension_of("resume.docx") == "docx"
    assert extension_of("resume") == ""


def test_has_allowed_extension():
    assert has_allowed_extension("resume.pdf")
    assert has_allowed_extension("resume.docx")
    assert not has_allowed_extension("resume.doc")
    assert not has_allowed_extension("resume.txt")


def test_is_within_size_limit():
    assert is_within_size_limit(b"x" * 1000, maximum_mb=10)
    assert is_within_size_limit(b"x" * (10 * 1024 * 1024), maximum_mb=10)
    assert not is_within_size_limit(b"x" * (10 * 1024 * 1024 + 1), maximum_mb=10)


def test_pdf_signature_check():
    assert matches_declared_signature("pdf", b"%PDF-1.4\n...")
    assert not matches_declared_signature("pdf", b"not a pdf at all")


def test_docx_signature_check_requires_zip_with_document_xml(sample_resumes_dir):
    real_docx = (sample_resumes_dir / "job1_good_gaps_analyst.docx").read_bytes()
    assert matches_declared_signature("docx", real_docx)

    # A plain ZIP that isn't a Word document (no word/document.xml) must fail.
    import zipfile
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("not_word.txt", "hello")
    assert not matches_declared_signature("docx", buffer.getvalue())

    # Plain text is not a ZIP at all.
    assert not matches_declared_signature("docx", b"just plain text")


def test_unknown_extension_never_matches_signature():
    assert not matches_declared_signature("doc", b"%PDF-1.4")


def test_validate_before_extraction_rejects_bad_extension():
    failure = validate_before_extraction("resume.doc", b"%PDF-1.4", maximum_mb=10)
    assert failure is not None
    assert failure.status == "unsupported"
    assert failure.code == "UNSUPPORTED_EXTENSION"


def test_validate_before_extraction_rejects_oversized_file():
    oversized = b"%PDF-1.4" + b"x" * (11 * 1024 * 1024)
    failure = validate_before_extraction("resume.pdf", oversized, maximum_mb=10)
    assert failure is not None
    assert failure.status == "unsupported"
    assert failure.code == "FILE_TOO_LARGE"


def test_validate_before_extraction_rejects_signature_mismatch():
    failure = validate_before_extraction(
        "resume.pdf", b"this is actually plain text", maximum_mb=10
    )
    assert failure is not None
    assert failure.status == "unsupported"
    assert failure.code == "SIGNATURE_MISMATCH"


def test_validate_before_extraction_passes_a_real_pdf(sample_resumes_dir):
    real_pdf = (sample_resumes_dir / "job1_strong_match_analyst.pdf").read_bytes()
    assert (
        validate_before_extraction(
            "job1_strong_match_analyst.pdf", real_pdf, maximum_mb=10
        )
        is None
    )


def test_is_probable_scan():
    assert is_probable_scan("short", min_extracted_chars=200)
    assert not is_probable_scan("x" * 200, min_extracted_chars=200)
    assert is_probable_scan("   " + "x" * 5 + "   ", min_extracted_chars=200)
