# Resume-Job-Matcher: Project Progress Tracker

**Status:** In Development  
**Current Checkpoint:** A (Stages 0-2 Complete)

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

### ⬜ Stage 3: Job Parser

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-2 complete

#### What Will Be Built

- Job description text → structured JobProfile
- Heading detection (Requirements, Responsibilities, Preferred)
- Requirement extraction with confidence scores
- Responsibility extraction with positions
- Minimum years extraction
- Support for varied heading styles

#### Acceptance Criteria

- "Must have SQL" → required qualification: SQL (importance=3)
- "Python is a plus" → preferred qualification: Python
- "Python is preferred" in Requirements section → overrides heading, marked preferred
- "3+ years" → minimum_relevant_years = 3.0
- Benefits text yields no qualifications
- All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 4: Resume Parser & PII Stripping

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-3 complete

#### What Will Be Built

- Resume text → structured CandidateProfile
- Section detection (summary, experience, education, skills, certifications)
- Evidence extraction with confidence scores
- 3-layer PII stripping (regex + spaCy NER + rules)
- Scanned PDF detection
- Parsing warnings (year-only dates, PMP-candidate, no headings, etc.)

#### Acceptance Criteria

- "PowerBI" normalized to "power bi"
- Skills in experience bullets = 1.00 confidence
- Skills in skills-section-only = 0.80 confidence
- Skills in summary = 0.90 confidence
- "PMP candidate" (not certified) flagged with warning, not held
- Year-only dates (e.g., "2020") parsed with lowered confidence
- Graduation year absent from scoring text
- Email, phone, name stripped before scoring
- All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 5: Qualification Matcher & Scorer

**Status:** NOT STARTED  
**Prerequisite:** Stages 0-4 complete

#### What Will Be Built

- Required/preferred qualification matching (skills, education, certs)
- Qualification score calculation (Section 11.2 formula)
- Evidence strength calculation
- Skill importance weighting

#### Acceptance Criteria

- Fixture score = 94.29 reproduced exactly
- Repeated skills counted once
- Empty category → `None` (not 0)
- Education level × field calculation (one-level-below = 0.50, somewhat-related = 0.75)
- All tests from SPECIFICATION.md Section 18.1 pass

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
| 3 | Job Parser | ⬜ NOT STARTED |
| 4 | Resume Parser & PII Stripping | ⬜ NOT STARTED |
| 5 | Qualification Matcher & Scorer | ⬜ NOT STARTED |
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
| parsing/job_parser.py | Job description parser | ⬜ Stage 3 |
| parsing/resume_parser.py | Resume parser + PII stripping | ⬜ Stage 4 |
| matching/scoring_engine.py | Scoring orchestration | ⬜ Stage 8 |
| ui/pages/*.py | Streamlit pages (5 pages) | ⬜ Stage 9 |
| README.md | User-facing documentation | ⬜ Stage 10 |

---

## Next Steps

1. ✅ Stages 0-2 complete and verified, locally and on GitHub
2. ⬜ **Start Stage 3** (Job Parser)
3. ⬜ Continue through Stages 4-10 in order
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

**Latest commit:** `c881240` - "Stage 2: add candidate ingestion service with transactional persistence"  
**Total commits:** 17  
**Branch:** main  
**Remote:** origin (https://github.com/ShreyasCuchcula/resume-job-matcher.git)

**File validation:**
- `requirements.txt`: 16 pinned dependencies
- `sample_data/jobs/`: 6 `.txt` files
- `sample_data/synthetic_resumes/`: 26 PDF/DOCX files
- `sample_data/expected_rankings.md`: ground truth for 3 jobs + full ingestion-status table
- `config/taxonomy/`: 178 skills, 5 degree levels, 13 fields, 26 certifications, 26 titles, 35 phrase mappings
- `db/models.py`: 13 ORM tables, 2 migrations applied
- `tests/`: 42 tests passing (unit + integration)
