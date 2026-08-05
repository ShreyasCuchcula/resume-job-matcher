# Resume-Job-Matcher: Project Progress Tracker

**Status:** In Development  
**Current Checkpoint:** B in progress (Stages 0-5 Complete)

---

## Overview

This document tracks detailed progress through all 10 implementation stages, with technical notes, verification steps, and troubleshooting guides for each stage. It serves as both a status tracker and a debugging reference.

**Architecture:** Clean layered Python application (UI → Services → Parsing/Matching → Normalization → Domain → DB)  
**Testing Strategy:** TDD (unit tests written before implementation); fixtures provide exact numeric ground truth  
**Version Control:** Git with clean, atomic commits; no tool co-authorship

---

## Checkpoint A: Foundation & Ingestion (Stages 0–2)

### ✅ Stage 0: Project Setup & Synthetic Data

**Status:** COMPLETE

#### What Was Built

1. **Project Folder Structure**
   - Module skeleton per SPECIFICATION.md Section 4: `config/`, `db/`, `domain/`, `ingestion/`, `parsing/`, `normalization/`, `matching/`, `services/`, `ui/` (with `pages/` and `components/`), `tests/` (with `unit/`, `integration/`, `acceptance/`, `fixtures/`), `sample_data/` (with `jobs/`, `synthetic_resumes/`)
   - Root files: `requirements.txt` (pinned dependencies), `.gitignore` (Python-specific: venv/, *.db, __pycache__, uploads/, .env), `.gitattributes` (forces *.pdf/*.docx/*.doc to binary), `.env.example` (DATABASE_URL, UPLOAD_DIR, SCORING_CONFIG_PATH, LOG_LEVEL), `setup.sh` (one-command setup: venv, pip install, spaCy model, .env bootstrap)

2. **Environment & Dependencies**
   - Python 3.13.7 (exceeds spec's 3.11+ requirement)
   - **Documented deviation:** spaCy pinned to `3.8.*` instead of the spec's `3.7.*` - spaCy 3.7 has no prebuilt wheel for Python 3.13 and fails to build from source; 3.8.x is API-compatible for this project's usage (sentence segmentation, lemmatization, PERSON NER) and has cp313 wheels.
   - `setup.sh`'s spaCy model download falls back to installing the model wheel directly via pip when `spacy download` fails on networks that intercept TLS to `raw.githubusercontent.com`.

3. **Synthetic Data Generator** (`sample_data/generate.py`, deterministic, fixed seed)
   - **6 job descriptions** (`sample_data/jobs/`), varied heading styles per Section 10.2:
     - `job_01_data_analyst_standard.txt` - standard Requirements/Responsibilities/Preferred headings
     - `job_02_data_analyst_altheadings.txt` - alternate headings, no preferred section
     - `job_03_data_engineer.txt` - Minimum Qualifications/Key Activities/Nice to Have
     - `job_04_bi_analyst.txt` - Must Have/The Role/Bonus Points, no experience minimum stated
     - `job_05_data_scientist.txt` - Requirements/Duties/Desired, includes a "degree or equivalent experience" clause
     - `job_06_software_engineer.txt` - What You Need/Responsibilities/A Plus, PMP as a preferred cert
   - **20 candidate resumes** (PDF via PyMuPDF, DOCX via python-docx) spanning: strong match, good-but-gaps, keyword-stuffer (skills list only, no evidence bullets), career-changer, missing dates, year-only dates, no section headings, table-based DOCX skills section, degree-or-equivalent, PMP-candidate
   - **6 deliberately broken ingestion edge cases** (`sample_data/synthetic_resumes/`):
     - `job1_strong_match_analyst_duplicate.pdf` - exact byte-for-byte duplicate of an accepted PDF (SHA-256 collision)
     - `edge_corrupt_file.pdf` - `.pdf` extension and `%PDF` header, but not a real PDF structure
     - `edge_password_protected.pdf` - valid, AES-256 encrypted PDF (`needs_pass` True)
     - `edge_probable_scan.pdf` - valid PDF, extracts to well under the 200-character minimum
     - `edge_renamed_txt_as_pdf.pdf` - plain text saved with a `.pdf` extension (fails the magic-byte check)
     - `edge_unsupported_filetype.doc` - legacy `.doc` extension, not in the allowed set
   - **26 total resume files**, all verified against the real extraction contracts at generation time

4. **`sample_data/expected_rankings.md`** - hand-reasoned acceptance-test ground truth: expected ingestion status for all 26 files, plus full ranked score walkthroughs (required/experience/responsibility/preferred/final) for 3 jobs (Data Analyst, Data Engineer, Data Scientist), cross-referenced against all 8 acceptance scenarios in Section 18.3

#### Known Issues & Resolutions

1. **spaCy 3.7 has no Python 3.13 wheel.** Resolved by pinning `spacy==3.8.*` (documented deviation, approved).
2. **`spacy download` fails behind TLS-intercepting networks** (`SSL_CERT_VERIFY_FAILED` hitting `raw.githubusercontent.com`). Resolved with a fallback in `setup.sh` that installs the model wheel directly via pip.
3. **Two small edge-case PDFs were being misdetected as text by git**, risking corruption via `autocrlf` on checkout. Resolved by adding `.gitattributes` forcing `*.pdf`/`*.docx`/`*.doc` to binary.
4. **Commits initially carried a tool co-author trailer.** Resolved: commit messages and authorship now show only the project author, with no trailers, going forward.

---

### ✅ Stage 1: Configuration & Taxonomies

**Status:** COMPLETE

#### What Was Built

1. **Taxonomies** (`config/taxonomy/`), self-validated as alias-collision-free at generation time:
   - `skills.json` - 178 canonical skills (programming languages, databases, BI tools, cloud/DevOps, ML/AI, data engineering, web frameworks, business tools) with aliases, categories, and taxonomy-approved `related_skills` partial-credit pairs
   - `degrees.json` - `high_school < associate < bachelor < master < doctorate` ladder with alias maps
   - `fields.json` - 13 fields of study with `related` (1.00) / `somewhat_related` (0.75) relatedness tiers, each direction listed explicitly
   - `certifications.json` - 26 certs/licenses with aliases and explicit equivalents/related partial-credit pairs
   - `titles.json` - 26 canonical job titles with aliases and `related_titles` for experience role-relevance matching
   - `phrase_normalization.json` - 35 controlled phrase mappings for TF-IDF pre-processing
   - `VERSION` - `tax-1.0`

2. **Domain layer** (`domain/`):
   - `enums.py` - `RequirementType`, `EvidenceSection`, `RunStatus`, `FileStatus`, `MissingItemStatus`, `EmploymentSectionType` (Literal aliases)
   - `exceptions.py` - `DomainError`, `ValidationError`, `ParsingError`, `CorruptFileError`, `UnscorableJobError`
   - `schemas.py` - every pydantic v2 model from SPECIFICATION.md Section 5, with `extra="forbid"` and validators enforcing every stated invariant (score ranges, importance ∈ {1,2,3}, non-empty evidence text, `applied_weights` summing to 1.0 ± 1e-9, final_score rounded to 2dp)

3. **Config** (`config/`):
   - `scoring.yaml` - weights, responsibility-matching thresholds, evidence-strength tiers, job-parsing confidence bands, upload limits, descriptive labels, matching Section 7.1 exactly
   - `settings.py` - pydantic-settings loader (`DATABASE_URL`, `UPLOAD_DIR`, `SCORING_CONFIG_PATH`, `LOG_LEVEL`); fail-fast `get_app_config()` validates weights/thresholds/labels and re-validates taxonomy alias-collision-freedom on load

4. **Database layer** (`db/`):
   - `base.py` - `GUID` TypeDecorator (native `UUID` on Postgres, `CHAR(36)` elsewhere), `portable_json()` (`JSON` on SQLite, `JSONB` on Postgres)
   - `session.py` - engine/sessionmaker factory built from settings
   - `models.py` - all 13 ORM tables from Section 6.1, with FKs, the `(run_id, candidate_id)` unique constraint, and CHECK constraints mirroring the domain enums/numeric ranges
   - Alembic initialized; migration `0001_initial_schema` creates the full schema

#### Verification

- Every fail-fast config branch tested directly: bad weight sum, negative weight, out-of-range threshold, non-descending labels, missing taxonomy file, invalid JSON, alias collision, missing VERSION file - each raises with a specific message.
- Migration round-trips cleanly on SQLite (upgrade/downgrade/upgrade); all 13 tables' DDL compiles cleanly against the PostgreSQL dialect, with `GUID` rendering as native `UUID` and JSON columns rendering as `JSONB`.
- Full ORM smoke test: insert across the whole graph (job → candidate → scoring run → match result → evidence/warnings), UNIQUE and CHECK constraints enforced at the DB level, cascade delete verified end-to-end (deleting a candidate removes its resumes, employment records, evidence bullets, qualifications, match results, match evidence, and scoring warnings, while leaving unrelated jobs untouched).

#### Known Issues & Resolutions

1. **Alembic's autogenerated migration 0001 had two missing imports** (`db.base` for the custom `GUID` type, `Text` for the JSONB `astext_type` argument) that would have raised `NameError` on a clean checkout. Fixed by adding the missing imports.

---

### ✅ Stage 2: Database & Ingestion Pipeline

**Status:** COMPLETE

#### What Was Built

1. **`ingestion/validation.py`** - pure, side-effect-free checks: extension allowlist, 10 MB size limit, magic-byte signature verification (PDF `%PDF`, DOCX ZIP containing `word/document.xml` - extension is never trusted alone), and the 200-character probable-scan threshold.
2. **`ingestion/pdf_reader.py`** - PyMuPDF extraction matching the exact Section 8.2 contract; raises `CorruptFileError("password-protected")` for encrypted PDFs and wraps any other extraction failure in the same exception type; `pdf_needs_password()` for a non-raising check.
3. **`ingestion/docx_reader.py`** - python-docx extraction matching the exact Section 8.2 contract; combines paragraph text and table-cell text into one stream.
4. **`ingestion/hashing.py`** - SHA-256 hashing, `{sha256}.{ext}` server-generated naming, duplicate-hash checking. Deliberately has no DB dependency, per the layering rule that only `services` may call `db`.
5. **`services/candidate_service.py`** - batch orchestration:
   - Runs every uploaded file through the full validation → hash/dedupe (within-batch and against every hash already persisted from a prior run) → extraction → probable-scan sequence, returning a per-file status/code/message for every file in the order given. One file's unexpected failure never stops the rest of the batch.
   - Persists every accepted file's `Candidate` + `Resume` row in a single DB transaction: the whole accepted set commits together or not at all. On failure, the transaction rolls back, every file written to `uploads/` during that call is removed, and the affected results are downgraded to `status="failed"`.
   - Display identifiers (`Candidate 001`, `Candidate 002`, ...) are assigned by ascending SHA-256 across the accepted batch, per Section 14.3.
6. **Migration `0002`** - makes `resumes.parsed_json` and `resumes.parser_version` nullable. Ingestion persists a resume as soon as text is extracted, before the resume parser (a later stage) exists to produce the full `CandidateProfile` those two columns hold; the parser will fill them in via an `UPDATE` once built. Verified via `batch_alter_table` (SQLite has no `ALTER COLUMN` and needs a table rebuild; on Postgres it compiles to a plain `ALTER COLUMN ... DROP NOT NULL`).
7. **Test suite** - `tests/conftest.py` (in-memory DB + sample-resumes fixtures) plus unit tests for every ingestion module and an integration suite running the full 26-file `sample_data` batch end-to-end. 42 tests total, all passing.

#### Verification

- All 26 synthetic files classified with the exact status documented in `expected_rankings.md`.
- Duplicate detection verified both within a single batch and across two separate batches against the DB.
- Display-identifier ordering, on-disk file naming, and DB row counts all verified against the real batch.
- Transactional rollback verified via a mocked `Session.commit()` failure: zero partial DB rows, zero orphaned files on disk, accurate per-file status reporting for the rest of the batch.
- Re-uploading an identical batch correctly marks every file as a duplicate against the DB with no new rows created.

#### Known Issues & Resolutions

1. **A pre-existing, stale `git rebase -i` state** (an abandoned interactive rebase with a leftover Vim swap file) was found in `.git/rebase-merge/`, predating this stage's work. It does not affect `HEAD` or branch history (confirmed: `HEAD` is a normal branch ref, and every commit/push since has worked correctly) but does make `git status` report a misleading "currently rebasing" message. **Do not run `git rebase --abort`** - its recorded `orig-head` is several commits behind current `main`, so an abort would hard-reset `main` backward and discard real, already-pushed work. If cleanup is wanted, the safe fix is deleting the stale directory directly: `rm -rf .git/rebase-merge`.

---

## Checkpoint B: Parsers & Scoring Brain (Stages 3–8)

### ✅ Stage 3: Job Parser

**Status:** COMPLETE

#### What Was Built

1. **`parsing/common.py` / `parsing/section_detector.py`** - shared bullet/sentence-splitting utilities (spaCy-backed, loaded lazily) and the job + resume heading dictionaries (Section 9.1/10.2) with punctuation-tolerant, case-insensitive heading detection and section splitting that reports whether any heading was found at all.
2. **`parsing/skill_extractor.py`, `education_extractor.py`, `certification_extractor.py`** - longest-match-first taxonomy matching over skills.json, degrees.json + fields.json, and certifications.json. Every short (2-4 char), purely alphabetic alias ("r", "go", "ml", "bs", "as", "cap") requires the matched text to be capitalized in the original - these collide with ordinary English words/prepositions in lowercase and would otherwise fire on unrelated prose. Field-of-study extraction matches known fields.json names directly rather than regex-capturing arbitrary text after "in", which broke on compound phrasing like "a quantitative field such as Statistics, Computer Science, or Data Science".
3. **`parsing/requirement_extractor.py`** - Section 10.3 required/preferred classification (explicit sentence cue beats section heading beats ambiguous), Section 10.4 importance assignment (3 = explicit must/mandatory/required wording, 2 = standard membership, 1 = weak/hedging), Section 10.5 extraction confidence (0.30 base + 0.25 taxonomy match + 0.20 cue + 0.15 heading + 0.10 exact degree/cert pattern), and duplicate merging.
4. **`parsing/job_parser.py`** - `extract_minimum_years()` (Section 10.6: "N+", "at least X", "minimum of X", range lower-bound, "N years of experience", written numbers zero-twenty, never inferred from "senior" alone); full `parse_job_description()` orchestration (Section 10.1 validation, heading-based extraction or the Section 10.2 no-headings sentence-by-sentence cue fallback, duplicate merging, "nothing scoreable" rejection); `confidence_band()` / `scoreable_requirements()` (Section 10.5's include/review/exclude table); the Section 10.8 confirmation-page data contract as pure functions (`add_requirement`, `edit_requirement`, `delete_requirement`, `reclassify_requirement`, `confirm_job_profile`) - the actual Streamlit page is Stage 9, but the data layer it will call is fully built and tested now.
5. **`parsing/responsibility_extractor.py`** - splits the responsibilities section into ordered, normalized items (Section 10.7, Section 12.2 steps 1-3).

#### Known Issues & Resolutions

1. **A bullet wrapped across two physical lines** (as `job_05_data_scientist.txt`'s degree requirement does) was being split into two unrelated fragments by the original line-based splitter, silently losing the "is required" cue and downgrading that item's importance/confidence. Fixed in `parsing/common.py`: a non-bulleted line following a bulleted one is now treated as a continuation of that bullet, not independent prose.
2. **A degenerate no-heading input (e.g. a long run of the same character, no spaces at all)** could slip past the "nothing scoreable" rejection, because the no-headings fallback treated any unclassified sentence as a responsibility candidate. Fixed by requiring a candidate responsibility sentence to contain at least one space (i.e., be more than a single token) in that fallback path.

#### Verification

Full `parse_job_description()` pipeline run against all 6 real synthetic job descriptions with detailed assertions on every required/preferred item, importance, confidence, minimum-years value, and responsibility ordering - all matching a hand-trace of Sections 10.2-10.6 against the actual file content. 150 tests total (unit + integration), all passing, including every Section 18.1 fixture ("must have SQL" -> required importance=3; "Python is a plus" -> preferred; "Python is preferred" inside a Requirements section -> preferred, wording beats heading; "3+ years" -> 3.0; "two to four years" -> 2.0; benefits text -> no qualifications; "senior" alone -> no minimum) plus dedicated coverage of Section 10.1 rejections and the no-headings fallback end to end.

---

### ✅ Stage 4: Resume Parser & PII Stripping

**Status:** COMPLETE

#### What Was Built

1. **`parsing/section_detector.py`** - fixed a naming inconsistency (RESUME_HEADINGS mapped "Projects"/"Certifications" to plural canonical names that didn't match the singular `EvidenceSection`/`EmploymentSectionType` domain enums from Stage 1) and verified the resume heading dictionary against all 26 synthetic resumes.
2. **`parsing/responsibility_extractor.py`** - gained `build_evidence_bullets()`/`extract_evidence_bullets()` (Section 9.2): the same bullet/continuation-line-aware splitting used for job responsibilities, producing `EvidenceBullet` objects linked to their employment role via `employment_id`.
3. **`parsing/skill_extractor.py`, `education_extractor.py`, `certification_extractor.py`** - resume-side extraction: `extract_candidate_skills()` (Section 9.3 evidence-strength tiers: bullet=1.00, summary=0.90, skills-section=0.80, strongest evidence wins), `extract_candidate_education()` (Section 9.5: degree + field, completion status, no graduation year ever), `extract_candidate_certifications()` (Section 9.6: held vs. pending wording, `PENDING_CREDENTIAL` warning).
4. **`normalization/dates.py`, `normalization/titles.py`, `parsing/employment_extractor.py`** - Section 9.7: date-range parsing (month-name, numeric, year-only, "Present"), role-block splitting, title normalization.
5. **`parsing/pii.py`** - three-layer PII stripping (Section 9.4): regex layer (email/phone/URL/address/DOB/age/gender/pronouns/marital/nationality), header layer (contact block above the first heading discarded outright), spaCy NER backstop for names appearing elsewhere.
6. **`parsing/resume_parser.py`** - full `parse_resume()` orchestration tying every extractor together into a `CandidateProfile`.
7. Scanned-PDF detection (`probable_scan` status, `min_extracted_chars` threshold) was already built in Stage 2's `ingestion/validation.py` - reverified still passing, no changes needed.

#### Known Issues & Resolutions

1. **A bullet wrapped across two physical lines** was misdetected as the start of a new employment role block (the same class of bug fixed for job parsing in Stage 3, but in a new function). Fixed by only treating a non-bulleted line as a new role header when it actually matches the "Title - Company (Dates)" shape.
2. **`degrees.json` had no bare "bachelor"/"master"/"associate"/"doctorate" alias**, so "Bachelor of Business Administration" (not an exact match for any curated phrase) failed to match at all, silently dropping that candidate's education record. Added bare-word aliases and several more spelled-out "Bachelor/Master of X" variants.
3. **spaCy's NER backstop misread proper-noun-shaped technology names** ("Python", "Docker", "Machine Learning") as PERSON entities, silently masking and deleting those skill mentions before extraction ever saw them - found by comparing extracted skills against the actual resume text. Fixed by adding a protected-terms parameter to `mask_person_entities()`; the full skill taxonomy vocabulary is now protected from NER masking.
4. **The no-headings fallback had no "education"/"certification" section to scan at all**, so a no-headings resume's degree or credential mention was never found even when clean and matchable. Fixed by having both extractors fall back to scanning the same unsectioned body the no-headings path already uses for bullets/skills.
5. **DOCX table content lands after all paragraph text** (Section 8.2's exact extraction contract), so a skills table ends up as trailing lines under whatever heading was last in the document. Added a targeted recovery heuristic: if the skills section came up empty and another section's last line looks like a bare comma-separated list, treat it as the orphaned table content.

#### Verification

All 21 real parseable synthetic resumes parse without error. Every Section 18.1 fixture this stage covers passes exactly. 6 of the 8 Section 18.3 acceptance scenarios verified at the extraction level (5 and 6 concern job-side/scoring behavior not built yet). Critically, the Section 9.4 name-swap invariant holds: re-parsing the same resume with only the candidate's name and email changed produces byte-identical skills/education/certifications/employment/evidence-bullet extraction - only the audit-only `raw_resume_text` field legitimately differs.

---

### ✅ Stage 5: Qualification Matcher & Scorer

**Status:** COMPLETE

#### What Was Built

1. **`matching/qualification_matcher.py`** - the full Section 11 matching engine:
   - `match_skill()` (Section 11.2) - exact/alias match keeps the candidate's own tiered evidence strength (1.00 bullet / 0.90 summary / 0.80 skills-section, set by Stage 4); failing that, a taxonomy-approved related skill (looked up under the *required* skill's own `related_skills` entry in skills.json) earns flat configured partial credit (default 0.50); otherwise a `not_identified` `MissingItem`.
   - `match_education()` (Section 11.3) - degree-level score (meets/exceeds=1.00, one level below=0.50, lower/absent=0.00) times field score (exact/related=1.00, somewhat-related=0.75, else 0.00), falling back to a single axis for level-only or field-only requirements; best-of across all of a candidate's education records (never mixes level from one record with field from another); "degree or equivalent experience" via `max(degree_match, min(relevant_years/equivalent_years, 1.0))`, with `relevant_years` left optional (Stage 7's experience scorer will supply the real value) and an unstated `equivalent_years` never invented - it raises an `EQUIVALENT_YEARS_NOT_STATED` warning instead.
   - `match_certification()` (Section 11.4) - exact credential (or taxonomy-approved equivalent), held = 1.00; taxonomy-approved related (non-equivalent) credential, held = configured partial; pending/preparing/coursework wording = 0.00 + `PENDING_CREDENTIAL` warning; not identified = 0.00 + `MISSING_REQUIRED_CREDENTIAL` recruiter-verification warning when the item is required (never auto-rejects). Applies identically to "certification" and "license" requirement types.
   - `match_qualifications()` - the single entry point for both required and preferred lists (Section 11.1: identical mechanics): `score = 100 * sum(importance_i * match_i) / sum(importance_i)`, rounded to 2dp; an empty requirements list returns `score=None` (inapplicable, never 0, never free points). Dispatches per `JobRequirement.type` to the three matchers above and assembles the `ComponentResult`.
2. **`matching/scoring_engine.py`** - `score_required_qualifications()` / `score_preferred_qualifications()`, each asserting `job.confirmed` (Section 10.8: "unconfirmed jobs cannot be scored" as a hard assertion in the engine, defense in depth alongside the UI-level gate later).

#### Known Issues & Resolutions

1. **The schema's `MissingItemStatus` enum has only three values** (`not_identified` / `unclear` / `pending_credential`) and the spec never states exactly which applies to which mismatch shape. Resolved by an explicit, consistent mapping: a skill/credential/education with zero matching evidence at all -> `not_identified`; an education record that exists but doesn't clearly satisfy the level/field requirement -> `unclear` (something education-shaped is present, it just isn't proof of absence either way); a credential found but not yet held -> `pending_credential`.
2. **No `legally_required` flag exists anywhere in the schema**, but Section 11.4 calls for a "verification warning when legally required" on a missing credential. Resolved by emitting `MISSING_REQUIRED_CREDENTIAL` whenever a certification/license requirement is `required=True` and not identified at all - approximating "legally required" with "required," the closest signal the schema actually carries - and never for preferred items or for skill/education types.
3. **skills.json/certifications.json store specific per-relation partial-credit weights** (e.g. `csm` -> `psm`: 0.8) rather than always deferring to scoring.yaml's single `related_default` (0.50). Resolved by using the taxonomy's own specific weight when present (falling back to the module-level default only if a relation is approved with no explicit weight) - consistent with Stage 3/4's precedent of hardcoding scoring-tier constants in the matching code itself rather than threading `ScoringConfig` through every call.

#### Verification

All 4 hand-built Section 11.5 worked fixtures reproduce exactly (94.29 required, 72.00 preferred), including via the real taxonomy-driven "related field" path, not just synthetic numbers. Integration-tested against every real parsed job description scored against every real parseable synthetic resume (6 jobs x 20 resumes, no crashes, every score in [0,100], every evidence item carries non-empty text) plus targeted scenario checks against `expected_rankings.md`: Job 6's PMP held-vs-pending distinction (Reese Chandler gets full preferred credit; Finley Osei's "PMP candidate" wording scores 0.00 with a `PENDING_CREDENTIAL` warning), Job 5's "or equivalent experience of 4 years" clause parses correctly off the real job text and resolves to full credit once a `relevant_years` value is supplied, and Job 2's missing preferred section yields `preferred_score=None` for both real candidates. 401 tests total, all passing; `ruff check .` clean.

---

### ⬜ Stage 6: Education Validator

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-5 complete

#### What Will Be Built

- Education requirement matching
- Degree level calculation
- Field-of-study relevance scoring
- "Degree or equivalent" clause handling

#### Acceptance Criteria

- Fixture score = 72.00 reproduced exactly
- "Degree or equivalent X years" satisfied through years_experience
- All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 7: Experience Scorer

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-6 complete

#### What Will Be Built

- Years-of-relevant-experience calculation
- Employment record interval merging (overlapping dates)
- Experience relevance formula (years_available / years_required)
- Date confidence assessment

#### Acceptance Criteria

- Fixture: 2.5 years / 3 required = 83.33% score
- Fixture: 5 years / 3 required = 100.00% score
- Overlapping intervals merged correctly: [2019-01 to 2021-06] + [2020-01 to 2022-01] = 3.0 years
- End-before-start discarded with warning
- No minimum stated → `None`
- All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 8: Responsibility Scorer & Final Score & Persistence

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-7 complete

#### What Will Be Built

- TF-IDF vectorizer (one per frozen batch)
- Responsibility matching via cosine similarity
- Dynamic weight normalization
- Final score calculation
- Scoring run persistence (SQLAlchemy + transactions)
- Evidence persistence (match_evidence, missing_items, warnings)

#### Acceptance Criteria

- Fixture: responsibility_score = 66.33 reproduced exactly
- Fixture: final_score = 83.17 reproduced exactly
- Fixture: applied_weights = {required: 0.5294, experience: 0.2353, responsibility: 0.2353} when preferred is absent
- Weights always sum to 1.0 ± 1e-9
- All four components present → defaults unchanged
- Preferred absent → redistribute across the other three (Section 13.5 formula)
- All-`None` → UnscorableJobError
- One TF-IDF vectorizer per run (asserted by object identity)
- Full run persistence in one transaction; any failure rolls back the entire run
- Re-runs on same data produce bit-identical results
- All tests from SPECIFICATION.md Section 18.1 & 18.2 pass

---

## Checkpoint C: UI, Export & Validation (Stages 9–10)

### ⬜ Stage 9: Streamlit UI (5 Pages)

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-8 complete

#### What Will Be Built

1. **Page 1: Create Job** - textarea for job description, "Analyze Description" button
2. **Page 2: Confirm Job** - extracted required/preferred/minimum years/responsibilities with confidence, edit/delete/reclassify, "Confirm and Continue" freezes the job
3. **Page 3: Upload Resumes** - multi-file uploader, per-file status table, "Score Candidates" button
4. **Page 4: Rankings** - ranked table, mandatory oversight notice (Section 17.3), CSV download
5. **Page 5: Candidate Details** - full score breakdown, evidence cards, missing items, warnings

#### Acceptance Criteria

- All 5 pages render without error
- Full recruiter flow demoable end-to-end on synthetic data in under 5 minutes
- Evidence display shows source text for every nonzero match
- Missing items clearly marked as unverified
- Warnings displayed with codes and messages
- Mandatory oversight notice present on rankings page
- CSV export matches persisted values exactly

---

### ⬜ Stage 10: Testing, Documentation & Polish

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-9 complete

#### What Will Be Built

1. **Unit tests** (Section 18.1): job parser, resume parser, qualification scorer, experience scorer, responsibility scorer, weight normalizer
2. **Integration tests** (Section 18.2): full path paste → parse → confirm → upload → score → persist → export; in-memory SQLite; one corrupt file doesn't block the batch; single shared vectorizer per run; injected DB failure leaves zero partial rows
3. **Acceptance tests** (Section 18.3): all 8 scenarios automated against `expected_rankings.md`, including the name-swap test
4. **Code quality**: `black .`, `ruff check .`, zero errors expected
5. **Documentation**: `README.md` (pitch, features, quick start, architecture, testing strategy, tech stack, Postgres switch guide, known limitations); this file updated to reflect final state

#### Acceptance Criteria

- All unit tests pass (Section 18.1 fixtures verified)
- All integration tests pass (Section 18.2 flow verified)
- All acceptance scenarios pass (Section 18.3 ground truth verified)
- Ruff clean, Black clean
- README complete and professional
- Definition of Done (SPECIFICATION.md Section 21) fully satisfied

---

## Troubleshooting & Common Issues

### Issue: Git Push Fails

**Symptom:**
```
fatal: could not read Username for 'https://github.com': No such file or directory
```

**Solution:**
```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
git push
```

---

### Issue: Virtual Environment Not Activating

**Symptom:** Terminal prompt doesn't show `(venv)` prefix after running activation

**Windows:**
```bash
venv\Scripts\activate
```

**Mac/Linux:**
```bash
source venv/bin/activate
```

Verify with:
```bash
which python  # Mac/Linux
where python  # Windows (PowerShell)
```

Should point to the `venv/` folder.

---

### Issue: Streamlit App Won't Start

**Symptom:**
```
ModuleNotFoundError: No module named 'streamlit'
```

**Solution:**
1. Verify venv is activated (should see `(venv)` prefix)
2. Reinstall requirements: `pip install -r requirements.txt`
3. Try again: `streamlit run app.py`

---

### Issue: Database Migration Fails

**Symptom:**
```
ERROR [alembic.migration] Can't locate revision identified by 'abc123'
```

**Solution:**
1. Check current head: `alembic current`
2. If needed, reset migrations:
   ```bash
   alembic downgrade base  # Go to empty DB
   alembic upgrade head    # Re-apply all migrations
   ```

---

### Issue: Tests Fail with Fixture Mismatch

**Symptom:**
```
AssertionError: 94.29 != 94.3
```

**Solution:**
1. Check rounding (should be 2 decimal places)
2. Verify component calculations in SPECIFICATION.md Sections 11–13
3. Check for missing importance weights

---

### Issue: `git status` reports an in-progress rebase that was never intentionally started

**Symptom:**
```
You are currently editing a commit while rebasing branch 'main' on '<hash>'.
```

**Solution:** Check `.git/rebase-merge/orig-head` before doing anything. If it points to a commit *behind* current `main` (i.e. real work has landed since), **do not run `git rebase --abort`** - it will hard-reset the branch back to that old commit. Instead remove the stale state directly: `rm -rf .git/rebase-merge` (and `.git/rebase-apply` if present). Confirm first that `.git/HEAD` reads `ref: refs/heads/main` (a normal branch ref, not a detached SHA) - if so, the rebase bookkeeping is orphaned and safe to delete.

---

## Stage Completion Status

| Stage | Description | Status |
|-------|-------------|--------|
| 0 | Project Setup & Synthetic Data | ✅ COMPLETE |
| 1 | Configuration & Taxonomies | ✅ COMPLETE |
| 2 | Database & Ingestion Pipeline | ✅ COMPLETE |
| 3 | Job Parser | ✅ COMPLETE |
| 4 | Resume Parser & PII Stripping | ✅ COMPLETE |
| 5 | Qualification Matcher & Scorer | ✅ COMPLETE |
| 6 | Education Validator | ⬜ NOT STARTED |
| 7 | Experience Scorer | ⬜ NOT STARTED |
| 8 | Responsibility Scorer, Final Score & Persistence | ⬜ NOT STARTED |
| 9 | Streamlit UI (5 Pages) | ⬜ NOT STARTED |
| 10 | Testing, Documentation & Polish | ⬜ NOT STARTED |

---

## Key Files Reference

| File | Purpose | Status |
|------|---------|--------|
| SPECIFICATION.md | Complete technical & functional spec | ✅ Ready |
| PROGRESS.md | This file; progress tracking | ✅ Ready |
| requirements.txt | Python dependencies (pinned) | ✅ Ready |
| setup.sh | One-command environment setup | ✅ Ready |
| sample_data/generate.py | Synthetic data generator | ✅ Ready |
| sample_data/expected_rankings.md | Ground truth for acceptance tests | ✅ Ready |
| config/settings.py | App configuration | ✅ Ready |
| config/scoring.yaml | Scoring weights & config | ✅ Ready |
| config/taxonomy/*.json | Skills, degrees, titles, etc. | ✅ Ready |
| domain/schemas.py | Pydantic data models | ✅ Ready |
| db/models.py | SQLAlchemy ORM models | ✅ Ready |
| db/migrations/versions/0001_initial_schema.py | Initial database schema | ✅ Ready |
| db/migrations/versions/0002_*.py | Nullable resume parse columns | ✅ Ready |
| ingestion/*.py | File validation, PDF/DOCX extraction, hashing | ✅ Ready |
| services/candidate_service.py | Batch ingestion orchestration | ✅ Ready |
| parsing/job_parser.py | Job description parser | ✅ Ready |
| parsing/section_detector.py, skill_extractor.py, education_extractor.py, certification_extractor.py, requirement_extractor.py, responsibility_extractor.py, common.py | Job parser support modules | ✅ Ready |
| parsing/resume_parser.py | Resume parser + PII stripping | ✅ Ready |
| parsing/pii.py, employment_extractor.py, normalization/dates.py, normalization/titles.py | Resume parser support modules | ✅ Ready |
| matching/qualification_matcher.py | Skill/education/certification matching + scoring formula | ✅ Ready |
| matching/scoring_engine.py | Required/preferred qualification scoring orchestration | ✅ Ready (experience/responsibility/final score: Stage 8) |
| ui/pages/*.py | Streamlit pages (5 pages) | ⬜ Stage 9 |
| README.md | User-facing documentation | ⬜ Stage 10 |

---

## Next Steps

1. ✅ Stages 0-5 complete and verified, locally and on GitHub
2. ⬜ **Start Stage 6** (Education Validator)
3. ⬜ Continue through Stages 7-10 in order
4. Update this file after each stage: flip status to `✅ COMPLETE`, document any issues encountered, keep the Stage Completion Status table current

---

## Notes for Future Debugging

### If Something Breaks in Stage N:

1. **Check PROGRESS.md** for that stage's acceptance criteria
2. **Run the relevant tests:**
   ```bash
   pytest tests/unit/test_<module>.py -v
   ```
3. **Check git log** to see what changed:
   ```bash
   git log --oneline -10
   git diff HEAD~1
   ```
4. **Refer to SPECIFICATION.md** Section referenced in the failed test
5. **Check the troubleshooting section above** for common issues
6. **Document the issue** in this file under that stage's "Known Issues & Resolutions" for future reference

---

## Repository Snapshot

**Latest commit:** `2bb6eef` - "Add scoring_engine integration + full-integration tests (Stage 5)"  
**Total commits:** 36  
**Branch:** main  
**Remote:** origin (https://github.com/ShreyasCuchcula/resume-job-matcher.git)

**File validation:**
- `requirements.txt`: 16 pinned dependencies
- `sample_data/jobs/`: 6 `.txt` files
- `sample_data/synthetic_resumes/`: 26 PDF/DOCX files
- `sample_data/expected_rankings.md`: ground truth for 3 jobs + full ingestion-status table
- `config/taxonomy/`: 178 skills, 5 degree levels, 13 fields, 26 certifications, 26 titles, 35 phrase mappings
- `db/models.py`: 13 ORM tables, 2 migrations applied
- `parsing/`: job description parser (Section 10) and resume parser (Section 9) both complete, across 12 modules
- `normalization/`: dates.py, titles.py
- `matching/`: qualification_matcher.py (skill/education/certification matching + Section 11.1 scoring formula), scoring_engine.py (required/preferred orchestration)
- `tests/`: 401 tests passing (unit + integration)
