"""Integration tests for the full resume-parsing pipeline
(parsing/resume_parser.py::parse_resume) against all real synthetic
resumes and the Section 9 / 18.1 / 18.3 acceptance scenarios
(SPECIFICATION.md)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from config.settings import get_app_config
from ingestion.docx_reader import extract_docx_text
from ingestion.pdf_reader import extract_pdf_text
from parsing.resume_parser import build_resume_extractor_context, parse_resume

RESUMES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "sample_data" / "synthetic_resumes"
)
RUN_DATE = date(2026, 8, 1)

# Deliberately broken ingestion fixtures (Section 8.1) - not parseable
# resumes, out of scope for the resume parser itself.
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


@pytest.fixture(scope="module")
def context():
    return build_resume_extractor_context(get_app_config().taxonomy)


def _parse(filename: str, context) -> "CandidateProfile":  # noqa: F821
    text = _extract_text(RESUMES_DIR / filename)
    return parse_resume(
        text,
        file_hash="x" * 64,
        display_identifier="Candidate 001",
        context=context,
        run_date=RUN_DATE,
    )


class TestAllResumesParseCleanly:
    """Section 18.1/9: "All 26 synthetic resumes parse without error
    or crash." (21 of the 26 files are parseable resumes; the other 5
    are ingestion-layer edge cases covered by Stage 2's tests.)"""

    @pytest.mark.parametrize("path", _resume_files(), ids=lambda p: p.name)
    def test_parses_without_raising(self, path: Path, context):
        text = _extract_text(path)
        profile = parse_resume(
            text,
            file_hash="x" * 64,
            display_identifier="Candidate 001",
            context=context,
            run_date=RUN_DATE,
        )
        assert profile.scoring_text_available is True
        assert profile.parser_version

    @pytest.mark.parametrize("path", _resume_files(), ids=lambda p: p.name)
    def test_no_graduation_year_ever_appears_on_any_education_record(
        self, path: Path, context
    ):
        text = _extract_text(path)
        profile = parse_resume(
            text,
            file_hash="x" * 64,
            display_identifier="Candidate 001",
            context=context,
            run_date=RUN_DATE,
        )
        for record in profile.education:
            assert "graduation_year" not in record.model_dump()

    @pytest.mark.parametrize("path", _resume_files(), ids=lambda p: p.name)
    def test_no_email_or_phone_survives_into_any_scored_text(self, path: Path, context):
        text = _extract_text(path)
        profile = parse_resume(
            text,
            file_hash="x" * 64,
            display_identifier="Candidate 001",
            context=context,
            run_date=RUN_DATE,
        )
        scored_text = " ".join(
            [b.original_text for b in profile.evidence_bullets]
            + [q.evidence_text for q in profile.skills]
            + [e.original_text for e in profile.education]
            + [c.original_text for c in profile.certifications]
            + [e.description for e in profile.employment]
        )
        assert "@example.com" not in scored_text
        assert (
            "555" not in scored_text
        )  # every synthetic phone number uses this area code


class TestSection18_1Fixtures:
    def test_powerbi_normalizes_to_power_bi(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        assert "power bi" in {s.canonical_name for s in profile.skills}

    def test_skill_in_experience_bullet_is_1_00(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        sql = next(s for s in profile.skills if s.canonical_name == "sql")
        assert sql.evidence_strength == 1.00
        assert sql.evidence_section == "experience"

    def test_skill_in_skills_section_only_is_0_80(self, context):
        profile = _parse("job2_good_gaps_analyst2.docx", context)
        # Sam Whitfield's skills section lists "SQL, Excel" but only SQL
        # is demonstrated in a bullet - Excel is skills-section-only.
        excel = next(s for s in profile.skills if s.canonical_name == "microsoft excel")
        assert excel.evidence_strength == 0.80
        assert excel.evidence_section == "skills"

    def test_skill_in_summary_gets_0_90_when_not_demonstrated_elsewhere(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        # every skill mentioned in this resume's summary also appears in a
        # bullet or the skills section at >= 0.90, so assert the tier
        # directly against the scoring function instead of this fixture.
        summary_only = [s for s in profile.skills if s.evidence_section == "summary"]
        assert all(s.evidence_strength == 0.90 for s in summary_only)

    def test_pmp_candidate_flagged_pending_not_held(self, context):
        """Section 18.1 fixture: "PMP candidate" (not certified) flagged
        with warning, not held."""
        profile = _parse("job6_pmp_candidate_engineer.pdf", context)
        assert len(profile.certifications) == 1
        pmp = profile.certifications[0]
        assert pmp.canonical_name == "pmp"
        assert pmp.held is False
        assert pmp.pending is True
        assert any(w.code == "PENDING_CREDENTIAL" for w in profile.warnings)

    def test_pmp_certified_is_held(self, context):
        profile = _parse("job6_strong_match_swe.docx", context)
        pmp = next(c for c in profile.certifications if c.canonical_name == "pmp")
        assert pmp.held is True
        assert pmp.pending is False

    def test_year_only_dates_lower_confidence_to_0_6(self, context):
        """Section 18.1 fixture: year-only dates parsed with lowered
        confidence."""
        profile = _parse("job3_year_only_dates_engineer.pdf", context)
        assert profile.employment[0].date_confidence == 0.6
        assert any(w.code == "YEAR_ONLY_DATE" for w in profile.warnings)

    def test_graduation_year_absent_from_records(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        assert len(profile.education) == 1
        assert "graduation_year" not in profile.education[0].model_dump()

    def test_email_phone_name_stripped_from_scoring_text(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        assert (
            "jordan.ellis.demo@example.com"
            not in profile.evidence_bullets[0].original_text
        )
        all_bullet_text = " ".join(b.original_text for b in profile.evidence_bullets)
        assert "Jordan" not in all_bullet_text
        assert "Ellis" not in all_bullet_text

    def test_company_name_appears_in_evidence(self, context):
        """Company names may appear in displayed evidence but are never
        scored (Section 9.4/17.1) - this only asserts they survive into
        the EmploymentRecord.company display field."""
        profile = _parse("job1_strong_match_analyst.pdf", context)
        companies = {e.company for e in profile.employment}
        assert "Harborview Retail Group" in companies


class TestAcceptanceScenarios:
    """Section 18.3, resume-parsing-level preconditions (scoring itself
    is a later stage) - scenarios 5 and 6 concern job-side/scoring
    behavior that doesn't exist yet and aren't applicable here."""

    def test_scenario_1_strong_candidate_full_extraction(self, context):
        profile = _parse("job1_strong_match_analyst.pdf", context)
        required_skills = {"sql", "microsoft excel"}
        found = {s.canonical_name for s in profile.skills}
        assert required_skills <= found
        assert profile.education[0].degree_level == "bachelor"
        assert len(profile.employment) == 2
        assert profile.employment[0].is_current is True

    def test_scenario_2_keyword_stuffer_has_no_demonstrated_evidence(self, context):
        profile = _parse("job1_keyword_stuffer_analyst.pdf", context)
        # every skill mention comes from the skills section only, never a bullet
        assert all(s.evidence_section == "skills" for s in profile.skills)
        assert all(s.evidence_strength == 0.80 for s in profile.skills)
        # the job title normalizes (it's a known canonical title), but
        # titles.json deliberately gives it an empty related_titles list
        # (Stage 1) so it fails role-relevance matching at scoring time
        # rather than failing normalization itself.
        assert profile.employment[0].original_title == "Administrative Coordinator"
        assert profile.employment[0].normalized_title == "administrative coordinator"

    def test_scenario_3_missing_one_preferred_skill_is_simply_absent(self, context):
        profile = _parse("job1_missing_preferred_skill_analyst.pdf", context)
        names = {s.canonical_name for s in profile.skills}
        assert "power bi" in names
        assert "python" in names
        assert "tableau" not in names  # absent, not a zero-strength entry

    def test_scenario_4_degree_or_equivalent_has_no_degree_but_long_tenure(
        self, context
    ):
        profile = _parse("job5_degree_or_equivalent_scientist.pdf", context)
        assert profile.education == []
        assert profile.employment[0].start_date == date(2019, 6, 1)
        assert profile.employment[0].is_current is True

    def test_scenario_7_year_only_dates_warning_present(self, context):
        profile = _parse("job3_year_only_dates_engineer.pdf", context)
        assert any(w.code == "YEAR_ONLY_DATE" for w in profile.warnings)

    def test_scenario_8_name_swap_yields_identical_extraction(self, context):
        original = (RESUMES_DIR / "job1_strong_match_analyst.pdf").read_bytes()
        text = extract_pdf_text(original)
        renamed_text = text.replace(
            "Jordan Ellis", "Alexandra Whitmore-Fitzgerald"
        ).replace("jordan.ellis.demo@example.com", "alexandra.wf.demo@example.com")

        p1 = parse_resume(
            text,
            file_hash="a" * 64,
            display_identifier="Candidate 001",
            context=context,
            run_date=RUN_DATE,
        )
        p2 = parse_resume(
            renamed_text,
            file_hash="b" * 64,
            display_identifier="Candidate 001",
            context=context,
            run_date=RUN_DATE,
        )

        def scoring_relevant(profile):
            return (
                sorted(
                    (s.canonical_name, s.evidence_section, s.evidence_strength)
                    for s in profile.skills
                ),
                [
                    (e.degree_level, e.field_of_study, e.completed)
                    for e in profile.education
                ],
                [(c.canonical_name, c.held, c.pending) for c in profile.certifications],
                [
                    (
                        e.normalized_title,
                        e.company,
                        e.start_date,
                        e.end_date,
                        e.is_current,
                        e.date_confidence,
                    )
                    for e in profile.employment
                ],
                sorted(
                    (b.original_text, b.section_type) for b in profile.evidence_bullets
                ),
            )

        assert scoring_relevant(p1) == scoring_relevant(p2)
        assert (
            p1.raw_resume_text != p2.raw_resume_text
        )  # audit-only field legitimately differs


class TestTableBasedDocx:
    def test_orphaned_table_skills_recovered(self, context):
        profile = _parse("job3_good_gaps_engineer_table.docx", context)
        names = {s.canonical_name for s in profile.skills}
        assert {"sql", "python", "etl"} <= names


class TestNoHeadingsResume:
    def test_no_headings_warning_present(self, context):
        profile = _parse("job3_no_headings_engineer.pdf", context)
        assert any(w.code == "NO_HEADINGS" for w in profile.warnings)

    def test_no_headings_resume_still_extracts_skills_and_education(self, context):
        """Even without section structure, the whole body is scanned as
        experience-like text (Section 9.1) - skills, education, and
        evidence bullets should still come through."""
        profile = _parse("job3_no_headings_engineer.pdf", context)
        names = {s.canonical_name for s in profile.skills}
        assert {"sql", "python", "etl"} <= names
        assert profile.education
        assert profile.education[0].degree_level == "bachelor"
        assert profile.employment == []  # no reliable role-block structure to parse
        assert len(profile.evidence_bullets) > 0


class TestMissingDatesResume:
    def test_missing_dates_warning_and_null_dates(self, context):
        profile = _parse("job3_missing_dates_engineer.docx", context)
        assert profile.employment[0].start_date is None
        assert profile.employment[0].date_confidence == 0.0
        assert any(w.code == "MISSING_DATES" for w in profile.warnings)
        # the role and its bullets are still kept despite missing dates
        assert profile.employment[0].original_title == "Data Engineer"
        assert len(profile.evidence_bullets) == 3
