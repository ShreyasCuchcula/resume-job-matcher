"""Integration tests for resume-side section detection
(SPECIFICATION.md Section 9.1) against every real synthetic resume."""

from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from parsing.common import split_lines
from parsing.section_detector import (
    RESUME_HEADINGS,
    detect_heading,
    split_into_sections,
)

RESUMES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "sample_data" / "synthetic_resumes"
)

# These are deliberately broken ingestion fixtures (Section 8.1), not
# parseable resumes - excluded from resume-parser-level testing.
NON_RESUME_FILES = {
    "edge_corrupt_file.pdf",
    "edge_password_protected.pdf",
    "edge_probable_scan.pdf",
    "edge_renamed_txt_as_pdf.pdf",
    "edge_unsupported_filetype.doc",
}


def _resume_files() -> list[Path]:
    return sorted(p for p in RESUMES_DIR.iterdir() if p.name not in NON_RESUME_FILES)


def _extract_text(path: Path) -> str:
    data = path.read_bytes()
    return extract_pdf_text(data) if path.suffix == ".pdf" else extract_docx_text(data)


KNOWN_HEADING_TEXTS = {
    "SUMMARY",
    "PROFESSIONAL EXPERIENCE",
    "TECHNICAL SKILLS",
    "EDUCATION",
    "CERTIFICATIONS",
}


@pytest.mark.parametrize("path", _resume_files(), ids=lambda p: p.name)
def test_every_known_heading_line_present_in_the_file_is_detected(path: Path):
    """Every ALL-CAPS heading line the generator actually writes
    (SUMMARY, PROFESSIONAL EXPERIENCE, TECHNICAL SKILLS, EDUCATION,
    CERTIFICATIONS) must be recognized wherever it appears - a direct
    check against real file content, rather than a heuristic guess at
    what "looks like" a heading."""
    text = _extract_text(path)
    for line in split_lines(text):
        if line in KNOWN_HEADING_TEXTS:
            assert (
                detect_heading(line, RESUME_HEADINGS) is not None
            ), f"{path.name}: known heading text not recognized: {line!r}"


def test_no_headings_resume_reports_false(sample_resumes_dir=RESUMES_DIR):
    text = _extract_text(RESUMES_DIR / "job3_no_headings_engineer.pdf")
    sections, has_headings = split_into_sections(text, RESUME_HEADINGS)
    assert has_headings is False


def test_standard_resume_reports_all_canonical_sections():
    text = _extract_text(RESUMES_DIR / "job1_strong_match_analyst.pdf")
    sections, has_headings = split_into_sections(text, RESUME_HEADINGS)
    assert has_headings is True
    assert "summary" in sections
    assert "experience" in sections
    assert "skills" in sections
    assert "education" in sections


def test_certifications_section_uses_singular_canonical_name():
    text = _extract_text(RESUMES_DIR / "job6_strong_match_swe.docx")
    sections, _ = split_into_sections(text, RESUME_HEADINGS)
    assert "certification" in sections
    assert any("PMP" in line for line in sections["certification"])
