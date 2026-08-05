"""Unit tests for ingestion/docx_reader.py (SPECIFICATION.md Section 8.2)."""

from __future__ import annotations

import pytest

from domain.exceptions import CorruptFileError
from ingestion.docx_reader import extract_docx_text


def test_extract_docx_text_returns_paragraph_content(sample_resumes_dir):
    file_bytes = (sample_resumes_dir / "job1_good_gaps_analyst.docx").read_bytes()
    text = extract_docx_text(file_bytes)
    assert "PROFESSIONAL EXPERIENCE" in text
    assert len(text) > 200


def test_extract_docx_text_includes_table_cells(sample_resumes_dir):
    """The table-based fixture puts its skills section in a Word table,
    not paragraphs - extraction must pull table-cell text too."""
    file_bytes = (
        sample_resumes_dir / "job3_good_gaps_engineer_table.docx"
    ).read_bytes()
    text = extract_docx_text(file_bytes)
    assert "SQL, Python, Data Pipelines" in text


def test_extract_docx_text_raises_on_non_docx_bytes():
    with pytest.raises(CorruptFileError):
        extract_docx_text(b"this is not a docx file at all")


def test_extract_docx_text_raises_on_plain_zip_without_word_part():
    import zipfile
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("not_word.txt", "hello")

    with pytest.raises(CorruptFileError):
        extract_docx_text(buffer.getvalue())
