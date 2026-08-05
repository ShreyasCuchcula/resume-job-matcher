"""Resume parsing orchestration (SPECIFICATION.md Section 9)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from domain.schemas import CandidateProfile, ParsingWarning
from normalization.titles import build_title_lookup
from parsing.certification_extractor import (
    build_certification_index,
    extract_candidate_certifications,
)
from parsing.education_extractor import (
    build_degree_index,
    build_field_index,
    extract_candidate_education,
)
from parsing.employment_extractor import extract_employment_records
from parsing.pii import strip_pii_from_lines
from parsing.responsibility_extractor import extract_evidence_bullets
from parsing.section_detector import RESUME_HEADINGS, split_into_sections
from parsing.skill_extractor import build_skill_index, extract_candidate_skills

PARSER_VERSION = "resume-parser-1.0"

_REDACTED_TOKEN = "[REDACTED]"
_BARE_LIST_ITEM_MAX_LEN = 30
_REDACTED_RESIDUE_RE = re.compile(r"[|,\s]+")


@dataclass(frozen=True)
class ResumeExtractorContext:
    skill_index: list
    degree_index: list
    field_index: list
    certification_index: list
    title_lookup: dict[str, str]
    phrase_normalization: dict[str, str]
    protected_ner_terms: frozenset[str]


def build_resume_extractor_context(taxonomy) -> ResumeExtractorContext:
    protected_terms = set()
    for canonical, meta in taxonomy.skills.items():
        protected_terms.add(canonical.lower())
        protected_terms.update(alias.lower() for alias in meta.get("aliases", []))

    return ResumeExtractorContext(
        skill_index=build_skill_index(taxonomy.skills),
        degree_index=build_degree_index(taxonomy.degrees),
        field_index=build_field_index(taxonomy.fields),
        certification_index=build_certification_index(taxonomy.certifications),
        title_lookup=build_title_lookup(taxonomy.titles),
        phrase_normalization=taxonomy.phrase_normalization,
        protected_ner_terms=frozenset(protected_terms),
    )


def _is_fully_redacted(line: str) -> bool:
    """True for a line that carries zero information once PII markers
    are removed (e.g. a lone masked name line: "[REDACTED]"). A
    contact line like "[REDACTED] | [REDACTED] | San Jose, CA" is NOT
    fully redacted - the city/state survives, and it isn't PII by
    itself."""
    if _REDACTED_TOKEN not in line:
        return False
    residue = _REDACTED_RESIDUE_RE.sub("", line.replace(_REDACTED_TOKEN, ""))
    return residue == ""


def _looks_like_bare_skill_list(line: str) -> bool:
    if not line or line.endswith("."):
        return False
    segments = [s.strip() for s in line.split(",")]
    if len(segments) < 2:
        return False
    return all(0 < len(s) <= _BARE_LIST_ITEM_MAX_LEN for s in segments)


def _recover_orphaned_table_content(
    sections: dict[str, list[str]]
) -> dict[str, list[str]]:
    """DOCX table content is appended after ALL paragraph text by
    extract_docx_text() (Section 8.2's exact contract), so a skills
    table ends up as trailing lines under whatever heading happened to
    be last in the document - not under "Skills". If the skills
    section came up empty and another section's last line looks like a
    bare comma-separated list (no sentence-ending period), treat it as
    the orphaned skills-table content instead of leaving it
    misclassified."""
    if sections.get("skills"):
        return sections
    for section_name in ("education", "certification", "research", "project"):
        lines = sections.get(section_name)
        if not lines:
            continue
        if _looks_like_bare_skill_list(lines[-1]):
            updated = dict(sections)
            updated[section_name] = lines[:-1]
            updated["skills"] = [lines[-1]]
            return updated
    return sections


def parse_resume(
    raw_text: str,
    *,
    file_hash: str,
    display_identifier: str,
    context: ResumeExtractorContext,
    run_date: date,
) -> CandidateProfile:
    """Section 9 end to end: detects sections, strips PII (the header
    layer here - dropping the pre-heading contact block outright - plus
    regex and NER layers via parsing.pii), extracts evidence bullets,
    skills (with evidence strength per section), education (no
    graduation year), certifications (held vs. pending), and employment
    (with date parsing and confidence). `raw_resume_text` is stored
    for audit only; nothing below this point ever extracts from it -
    every extractor only ever sees the PII-stripped section content.
    """
    warnings: list[ParsingWarning] = []

    if not raw_text or not raw_text.strip():
        return CandidateProfile(
            display_identifier=display_identifier,
            file_hash=file_hash,
            raw_resume_text=raw_text or "",
            scoring_text_available=False,
            parser_version=PARSER_VERSION,
            warnings=[
                ParsingWarning(
                    code="NO_HEADINGS",
                    message="Resume text is empty.",
                    source_text=None,
                )
            ],
        )

    sections, has_headings = split_into_sections(raw_text, RESUME_HEADINGS)

    if has_headings:
        # Section 9.4 layer 2: the contact block (everything above the
        # first heading) is discarded outright, never scanned at all.
        body_sections = {
            name: lines for name, lines in sections.items() if name != "unsectioned"
        }
    else:
        warnings.append(
            ParsingWarning(
                code="NO_HEADINGS",
                message="No section headings detected; entire body treated as unsectioned experience-like text.",
                source_text=None,
            )
        )
        body_sections = {"experience": sections.get("unsectioned", [])}

    body_sections = _recover_orphaned_table_content(body_sections)

    cleaned_sections: dict[str, list[str]] = {}
    for name, lines in body_sections.items():
        stripped = strip_pii_from_lines(lines, context.protected_ner_terms)
        cleaned_sections[name] = [
            line for line in stripped if line.strip() and not _is_fully_redacted(line)
        ]

    if has_headings:
        employment_records, employment_bullets, employment_warnings = (
            extract_employment_records(
                cleaned_sections.get("experience", []),
                title_lookup=context.title_lookup,
                run_date=run_date,
                phrase_map=context.phrase_normalization,
            )
        )
        warnings.extend(employment_warnings)
    else:
        # No headings means no reliable "Title - Company (Dates)" role
        # structure to parse - the whole body is kept as sentence-level
        # evidence instead of risking one bogus EmploymentRecord per line.
        employment_records = []
        employment_bullets = extract_evidence_bullets(
            cleaned_sections.get("experience", []),
            "employment",
            employment_id=None,
            phrase_map=context.phrase_normalization,
        )

    project_bullets = extract_evidence_bullets(
        cleaned_sections.get("project", []),
        "project",
        phrase_map=context.phrase_normalization,
    )
    research_bullets = extract_evidence_bullets(
        cleaned_sections.get("research", []),
        "research",
        phrase_map=context.phrase_normalization,
    )
    evidence_bullets = employment_bullets + project_bullets + research_bullets

    skills = extract_candidate_skills(
        bullet_texts_by_section={
            "experience": [b.original_text for b in employment_bullets],
            "project": [b.original_text for b in project_bullets],
            "research": [b.original_text for b in research_bullets],
        },
        summary_text=" ".join(cleaned_sections.get("summary", [])) or None,
        skills_section_text=" ".join(cleaned_sections.get("skills", [])) or None,
        skill_index=context.skill_index,
    )

    # No-headings resumes have no dedicated "education"/"certification"
    # section keys at all - the whole body ("experience") is the only
    # place a degree or credential mention could be, so it's scanned
    # there instead of coming up empty by construction.
    education_lines = cleaned_sections.get("education") or (
        [] if has_headings else cleaned_sections.get("experience", [])
    )
    certification_lines = cleaned_sections.get("certification") or (
        [] if has_headings else cleaned_sections.get("experience", [])
    )

    education = extract_candidate_education(
        education_lines, context.degree_index, context.field_index
    )

    certifications, certification_warnings = extract_candidate_certifications(
        certification_lines, context.certification_index
    )
    warnings.extend(certification_warnings)

    scoring_text_available = bool(
        skills or education or certifications or evidence_bullets
    )

    return CandidateProfile(
        display_identifier=display_identifier,
        file_hash=file_hash,
        raw_resume_text=raw_text,
        scoring_text_available=scoring_text_available,
        skills=skills,
        education=education,
        certifications=certifications,
        employment=employment_records,
        evidence_bullets=evidence_bullets,
        warnings=warnings,
        parser_version=PARSER_VERSION,
    )
