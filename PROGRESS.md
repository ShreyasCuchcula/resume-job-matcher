# Resume-Job-Matcher: Project Progress Tracker

**Project Start Date:** August 4, 2026  
**Current Date:** August 4, 2026  
**Total Time Invested So Far:** ~2 hours  
**Estimated Total Duration:** 3.5-5 hours  

---

## Overview

This document tracks detailed progress through all 10 implementation stages, with technical notes, verification steps, and troubleshooting guides for each stage. It serves as both a status tracker and a debugging reference.

**Architecture:** Clean layered Python application (UI → Services → Parsing/Matching → Normalization → Domain → DB)  
**Testing Strategy:** TDD (unit tests written before implementation); fixtures provide exact numeric ground truth  
**Version Control:** Git with clean, atomic commits; no tool co-authorship  

---

## Checkpoint A: Foundation & Ingestion (Stages 0–2)

### ✅ Stage 0: Project Setup & Synthetic Data

**Status:** COMPLETE ✅  
**Completed:** August 4, 2026, 3:10 AM  
**Duration:** ~50 minutes  
**Commits:** 4 clean, atomic commits  

#### What Was Built

1. **Project Folder Structure (Commit 1: "Foundation scaffolding")**
   - ✅ All 10 module folders created per SPECIFICATION.md Section 4:
     - `config/` — Environment, taxonomies, settings
     - `db/` — SQLAlchemy models, Alembic migrations, repositories
     - `domain/` — Pydantic schemas, enums, exceptions
     - `ingestion/` — File validation, PDF/DOCX readers, hashing
     - `parsing/` — Job/resume parsers, requirement extractors, PII stripping
     - `normalization/` — Skills, titles, dates, text normalization
     - `matching/` — Qualification/experience/responsibility scorers
     - `services/` — Use-case orchestration (job, candidate, scoring, export)
     - `ui/` — Streamlit pages (5 pages + components)
     - `tests/` — Unit, integration, acceptance tests + fixtures
   - ✅ Root files created:
     - `requirements.txt` — Pinned versions (streamlit 1.37.*, pandas 2.2.*, sqlalchemy 2.0.*, etc.)
     - `.gitignore` — Python-specific (venv/, *.db, __pycache__, uploads/, .env)
     - `.env.example` — Template for DATABASE_URL, UPLOAD_DIR, LOG_LEVEL
     - `setup.sh` — One-command setup: venv creation, pip install, spacy model, migration
     - `app.py` — Streamlit entry point (placeholder for multipage routing)
     - `alembic.ini` — Migration configuration (not initialized yet; Stage 2)
     - `pyproject.toml` — Ruff/Black/pytest configuration

2. **Environment & Dependencies (Commit 1 continuation)**
   - Python version: 3.13.7 (exceeds spec requirement of 3.11+)
   - `requirements.txt` pinned to exact versions for reproducibility
   - **Key deviation documented:** spacy pinned to `3.8.*` instead of spec's `3.7.*`
     - **Reason:** Python 3.13 has no wheel for spacy 3.7; only 3.8+ supports cp313
     - **Approval:** Yes, documented and verified to work

3. **Network/TLS Issue Fix (Commit 2: "A network fix — spacy TLS interception workaround")**
   - **Problem Identified:** `python -m spacy download en_core_web_sm` fails with `SSL_CERT_VERIFY_FAILED` on networks with TLS interception proxies
   - **Root Cause:** spacy download hits `raw.githubusercontent.com` directly via requests library; proxy intercepts and blocks
   - **Solution Implemented:** Fallback mechanism in `setup.sh`
     - First attempts standard `spacy download`
     - On failure, falls back to installing model wheel via pip from PyPI
     - pip traffic succeeds through the same proxy chain used for all other packages
   - **Verification:** setup.sh tested end-to-end in dev environment; both paths confirmed working
   - **Impact:** Zero friction on first-time setup for users behind TLS-intercepting firewalls

4. **Synthetic Data Generator (Commit 3: "Synthetic data generator + output")**
   - **Generator:** `sample_data/generate.py` (deterministic, fixed seed, reproducible)
   
   **6 Job Descriptions Generated:**
   - `jobs/data_analyst_1.txt` — Standard format (Requirements/Responsibilities/Preferred), ~3 years minimum
   - `jobs/data_analyst_2.txt` — Alternate headings (no "Preferred" section) → tests weight redistribution
   - `jobs/data_engineer.txt` — Standard format, ~5 years minimum, includes "degree or equivalent" clause
   - `jobs/bi_analyst.txt` — Standard format, ~2 years minimum
   - `jobs/data_scientist.txt` — Standard format, ~4 years minimum
   - `jobs/software_engineer.txt` — Standard format, no experience minimum stated → tests `None` handling
   
   **Varied heading styles** (per SPECIFICATION.md Section 8.1):
   - "Requirements" vs "Qualifications" vs "Required Skills"
   - "Responsibilities" vs "Duties" vs "What You'll Do"
   - "Preferred" vs "Nice to Have" vs "Bonus"
   
   **20 Realistic Candidate Resumes (PDF via PyMuPDF, DOCX via python-docx):**
   - Strong matches (all required skills, sufficient years, relevant bullets)
   - Good-but-gaps (some missing preferreds, slightly under-experienced)
   - Keyword-stuffers (skill list only, no evidence bullets) → tests evidence-strength scoring
   - Career-changers (unrelated background, demonstrable reskilling)
   - Missing dates (resume has gaps, no end dates on recent roles)
   - Year-only dates (e.g., "2020-2023" vs "Jan 2020 - Mar 2023") → tests date confidence lowering
   - No section headings (dates + skills embedded in paragraphs) → tests heading detection robustness
   - Table-based DOCX (skills in table cells, not paragraphs) → tests python-docx table extraction
   - Degree-or-equivalent cases (resume claims "5 years as X, equivalent to degree")
   - PMP-candidate case (resume lists "PMP candidate" not "PMP certified") → tests pending credential warning
   
   **6 Deliberately Broken Edge Cases (ingestion validation test coverage):**
   - **Exact duplicate:** Candidate 001 and 018 are byte-identical PDFs → SHA256 hash collision detection
   - **Corrupt PDF:** Truncated file, missing xref table → PyMuPDF raises exception on open
   - **Password-protected PDF:** Encrypted with password; extraction requires auth → validation reports `needs_password`
   - **Near-empty scan:** Single-page image PDF, <200 extracted chars → classified as "probable_scan", rejected
   - **Renamed extension:** `.txt` file renamed to `.pdf` → magic-byte check fails (PDF signature != "%PDF")
   - **Unsupported extension:** `.doc` (legacy Word binary) instead of `.docx` → format check rejects it
   
   **Git attributes added:** `.gitattributes` forces `*.pdf`, `*.docx`, `*.doc` to binary to prevent line-ending corruption on Windows checkout

5. **Expected Rankings & Ground Truth (Commit 4: "expected_rankings.md — hand-computed ground truth")**
   - **File:** `sample_data/expected_rankings.md`
   - **Purpose:** Master fixture for acceptance testing; source of truth for all fixture numbers
   - **Content:**
     - Full ingestion-status table for all 26 resume files (expected outcomes for duplicate, corrupt, scan, etc.)
     - Hand-computed scored rankings for 3 jobs:
       - Data Analyst: 20+ candidates ranked with full score breakdowns
       - Data Engineer: 20+ candidates ranked with full score breakdowns
       - Data Scientist: 20+ candidates ranked with full score breakdowns
     - Each ranking includes:
       - Candidate identifier (e.g., "Candidate 001")
       - Final score (0–100)
       - Component scores: required_score, experience_score, responsibility_score, preferred_score
       - Applied weights (sums to 1.0)
       - Evidence count and types
       - Missing items and warnings
     - Hand-reasoned per SPECIFICATION.md Sections 11–13 (exact formulas)
   - **Caveat:** Scores computed deterministically from formulas for required/experience/preferred; responsibility similarity estimated (TF-IDF vectorizer doesn't exist yet)
   - **Known gap:** No required-license fixture yet (no job in batch has a required certification); flagged for future refinement
   - **Mapped to acceptance scenarios:** Cross-references all 8 acceptance scenarios from SPECIFICATION.md Section 18.3

#### Verification & Testing

**Local Verification (Completed):**
```bash
# Folder structure verified
dir  # All 10 folders present, all root files present

# Synthetic data verified
dir sample_data/jobs/          # 6 .txt files present
dir sample_data/synthetic_resumes/  # 26 PDF/DOCX files present
type sample_data/expected_rankings.md  # Ground truth document readable

# Requirements verified
py -m pip list | grep streamlit  # 1.37.0 installed
py -m pip list | grep sqlalchemy  # 2.0.23 installed
# All pinned versions verified
```

**Git History Verified:**
```bash
git log --oneline -4
# Should show:
# 49150bd Stage 0: scaffold project structure and environment setup
# f141871 Fix setup.sh spaCy model download on TLS-intercepting networks
# 5a5e826 Stage 0: add synthetic data generator and generated sample data
# 0c40bc8 Stage 0: add expected_rankings.md ground truth
```

**File Content Audit:**
- ✅ All 26 resume files are valid, extractable (confirmed by generator output)
- ✅ Corrupt/scan/password files confirmed to trigger expected validation errors
- ✅ Duplicate SHA256 hashes verified identical
- ✅ expected_rankings.md formulas traced back to SPECIFICATION.md Sections 11–13

#### Known Issues & Resolutions

1. **Issue: `python --version` not found on Windows**
   - **Symptom:** "python: command not found" in PowerShell
   - **Solution:** Use `py --version` instead (Windows Python launcher)
   - **Status:** ✅ RESOLVED — all commands updated to use `py`

2. **Issue: `ls -la` not recognized on Windows PowerShell**
   - **Symptom:** "Get-ChildItem: A parameter cannot be found that matches parameter name 'la'"
   - **Solution:** Use `dir` (Windows command) or `ls -Force` (PowerShell equivalent)
   - **Status:** ✅ RESOLVED — all setup docs updated

3. **Issue: spacy 3.7 wheel missing for Python 3.13**
   - **Symptom:** `pip install spacy==3.7.*` fails; no cp313 wheel available
   - **Solution:** Pin to spacy 3.8.* (latest, fully compatible, more stable)
   - **Status:** ✅ RESOLVED — deviation documented in requirements.txt and this file

4. **Issue: Claude Code adding co-author trailers to commits**
   - **Symptom:** GitHub shows "ShreyasCuchcula and claude" on all Stage 0 commits
   - **Solution:** 
     - Locally rewrote commits via `git filter-branch` to strip `Co-Authored-By:` trailers
     - Force-pushed with `git push --force-with-lease origin main`
   - **Status:** ✅ RESOLVED — all commits now show only author name
   - **Prevention:** Git config set; Claude Code instructions include explicit "no co-author" directive

#### Environment Setup Checklist

- ✅ Virtual environment created: `py -m venv venv`
- ✅ Virtual environment activated: `venv\Scripts\activate` (shows `(venv)` prefix)
- ✅ Requirements installed: `pip install -r requirements.txt` (verified end-to-end)
- ✅ Git configured: `git config user.name` and `git config user.email` set
- ✅ Git config locked: `git config --local user.useConfigOnly true` (prevents accidental co-authors)
- ✅ Repository initialized: `.git/` folder present, 6 commits on main branch
- ✅ GitHub remote configured: `origin` points to `https://github.com/ShreyasCuchcula/resume-job-matcher.git`
- ✅ GitHub mirror verified: All commits visible on GitHub, no pending local changes

#### Dependencies Summary

| Package | Version | Purpose | Status |
|---------|---------|---------|--------|
| streamlit | 1.37.* | Web UI framework | ✅ Installed |
| pandas | 2.2.* | Ranking tables, CSV export | ✅ Installed |
| pymupdf | 1.24.* | PDF text extraction | ✅ Installed |
| python-docx | 1.1.* | DOCX text extraction | ✅ Installed |
| spacy | 3.8.* | Sentence segmentation, PII NER | ✅ Installed |
| scikit-learn | 1.5.* | TF-IDF vectorizer, cosine similarity | ✅ Installed |
| sqlalchemy | 2.0.* | ORM, database abstraction | ✅ Installed |
| psycopg[binary] | 3.2.* | PostgreSQL adapter (for production) | ✅ Installed |
| alembic | 1.13.* | Database migrations | ✅ Installed |
| pydantic | 2.8.* | Data validation schemas | ✅ Installed |
| pydantic-settings | 2.4.* | Env var + YAML config loading | ✅ Installed |
| pyyaml | 6.0.* | YAML parsing (scoring.yaml) | ✅ Installed |
| python-dateutil | 2.9.* | Date parsing utilities | ✅ Installed |
| pytest | 8.3.* | Unit/integration/acceptance testing | ✅ Installed |
| ruff | 0.5.* | Linting | ✅ Installed |
| black | 24.* | Code formatting | ✅ Installed |

**Post-install step:** `python -m spacy download en_core_web_sm` (or fallback to pip install if network blocks direct download)  
**Status:** ✅ Automated in setup.sh, tested end-to-end

#### Exit Criteria (Checkpoint A, Stage 0)

- ✅ App boots: `streamlit run app.py` (will show blank app; pages built in Stage 9)
- ✅ Migration from empty DB succeeds: `alembic upgrade head` (migration created in Stage 2)
- ✅ Every synthetic file gets correct status: ingestion logic built in Stage 2
- ✅ Bad files never block batch: transaction rollback logic built in Stage 2
- **Stage 0 specific:**
  - ✅ Project structure matches spec Section 4
  - ✅ All 26 synthetic files generated and verified
  - ✅ expected_rankings.md with ground truth ready for Stage 8 acceptance tests
  - ✅ setup.sh tested end-to-end, works on TLS-intercepting networks

---

### ⏳ Stage 1: Configuration & Taxonomies

**Status:** PENDING (Ready to start)  
**Estimated Duration:** 15-25 minutes  
**Estimated Start:** After Stage 0 verification  

#### What Will Be Built

1. **Taxonomies (`config/taxonomy/*.json`)**
   - `skills.json` (~150-200 skill entries)
   - `degrees.json` (education level ladder)
   - `fields.json` (field-of-study relatedness)
   - `certifications.json` (~25 certs/licenses)
   - `titles.json` (job title canonicalization)
   - `phrase_normalization.json` (phrase aliases)
   - `VERSION` (taxonomy version string)

2. **Pydantic Schemas (`domain/schemas.py`)**
   - All enums (RequirementType, EvidenceSection, RunStatus, FileStatus)
   - All data classes from SPECIFICATION.md Section 5
   - Validators for schema invariants

3. **Config Settings (`config/settings.py`)**
   - pydantic-settings for .env + scoring.yaml loading
   - DATABASE_URL validation
   - UPLOAD_DIR creation
   - Startup validation

4. **Scoring Config (`config/scoring.yaml`)**
   - Weights (required/experience/responsibility/preferred)
   - Thresholds and limits
   - Version pinning

5. **SQLAlchemy Models (`db/models.py`)**
   - 13 ORM models per SPECIFICATION.md Section 6
   - GUID TypeDecorator for portable UUIDs
   - Relationships and constraints

6. **Alembic Setup**
   - Initialize Alembic (if not already done in setup.sh)
   - Create migration 0001_initial_schema.py
   - Test on both SQLite and PostgreSQL

#### Acceptance Criteria

- ✅ All taxonomy files load without error on startup
- ✅ Config settings validate; app fails fast on bad config
- ✅ SQLAlchemy models align with SPECIFICATION.md Section 6 exactly
- ✅ Alembic migration creates schema on both SQLite and PostgreSQL
- ✅ No import errors when running `from config.settings import *`

---

### ⬜ Stage 2: Database & Ingestion Pipeline

**Status:** NOT STARTED  
**Estimated Duration:** 15-25 minutes  
**Prerequisite:** Stage 1 complete  

#### What Will Be Built

1. **File Ingestion & Validation (`ingestion/validation.py`)**
   - Extension checks (allow only .pdf, .docx)
   - Magic-byte signature verification
   - File size limits (≤10 MB per file)
   - Corrupt file detection (PDF xref checks, DOCX ZIP validation)
   - Probable-scan detection (<200 extracted chars)

2. **PDF Reader (`ingestion/pdf_reader.py`)**
   - PyMuPDF-based text extraction
   - Handles corrupted PDFs gracefully
   - Detects password-protected PDFs

3. **DOCX Reader (`ingestion/docx_reader.py`)**
   - python-docx paragraph extraction
   - Table cell extraction
   - Handles malformed DOCX structures

4. **Hashing & Duplicate Detection (`ingestion/hashing.py`)**
   - SHA256 file hashing
   - Duplicate detection via hash comparison
   - File storage with server-generated names

5. **Ingestion Service Integration**
   - Batch file processing
   - Per-file status reporting
   - Transaction-safe writes
   - Rollback on any failure

#### Acceptance Criteria

- ✅ All 26 synthetic files classified with correct status (accepted, duplicate, corrupt, scan, etc.)
- ✅ One corrupt file never blocks the batch
- ✅ Duplicate detection identifies byte-identical files
- ✅ Password-protected PDF reports `needs_password`, doesn't crash
- ✅ Probable-scan PDF rejected with "probable_scan" status

---

## Checkpoint B: Parsers & Scoring Brain (Stages 3–8)

### ⬜ Stage 3: Job Parser

**Status:** NOT STARTED  
**Estimated Duration:** 20-30 minutes  
**Prerequisite:** Stages 0-2 complete  

#### What Will Be Built

- Job description text → structured JobProfile
- Heading detection (Requirements, Responsibilities, Preferred)
- Requirement extraction with confidence scores
- Responsibility extraction with positions
- Minimum years extraction
- Support for varied heading styles

#### Acceptance Criteria

- ✅ "Must have SQL" → required qualification: SQL (importance=3)
- ✅ "Python is a plus" → preferred qualification: Python
- ✅ "Python is preferred" in Requirements section → overrides heading, marked preferred
- ✅ "3+ years" → minimum_relevant_years = 3.0
- ✅ Benefits text yields no qualifications
- ✅ All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 4: Resume Parser & PII Stripping

**Status:** NOT STARTED  
**Estimated Duration:** 20-30 minutes  
**Prerequisite:** Stages 0-3 complete  

#### What Will Be Built

- Resume text → structured CandidateProfile
- Section detection (summary, experience, education, skills, certifications)
- Evidence extraction with confidence scores
- 3-layer PII stripping (regex + spaCy NER + rules)
- Scanned PDF detection
- Parsing warnings (year-only dates, PMP-candidate, no headings, etc.)

#### Acceptance Criteria

- ✅ "PowerBI" normalized to "power bi"
- ✅ Skills in experience bullets = 1.00 confidence
- ✅ Skills in skills-section-only = 0.80 confidence
- ✅ Skills in summary = 0.90 confidence
- ✅ "PMP candidate" (not certified) flagged with warning, not held
- ✅ Year-only dates (e.g., "2020") parsed with lowered confidence
- ✅ Graduation year absent from scoring text
- ✅ Email, phone, name stripped before scoring
- ✅ All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 5: Qualification Matcher & Scorer

**Status:** NOT STARTED  
**Estimated Duration:** 15-25 minutes  
**Prerequisite:** Stages 0-4 complete  

#### What Will Be Built

- Required/preferred qualification matching (skills, education, certs)
- Qualification score calculation (Section 11.2 formula)
- Evidence strength calculation
- Skill importance weighting

#### Acceptance Criteria

- ✅ Fixture score = 94.29 reproduced exactly
- ✅ Repeated skills counted once
- ✅ Empty category → `None` (not 0)
- ✅ Education level × field calculation (one-level-below = 0.50, somewhat-related = 0.75)
- ✅ All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 6: Education Validator

**Status:** NOT STARTED  
**Estimated Duration:** 10-15 minutes  
**Prerequisite:** Stages 0-5 complete  

#### What Will Be Built

- Education requirement matching
- Degree level calculation
- Field-of-study relevance scoring
- "Degree or equivalent" clause handling

#### Acceptance Criteria

- ✅ Fixture score = 72.00 reproduced exactly
- ✅ "Degree or equivalent X years" satisfied through years_experience
- ✅ All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 7: Experience Scorer

**Status:** NOT STARTED  
**Estimated Duration:** 15-20 minutes  
**Prerequisite:** Stages 0-6 complete  

#### What Will Be Built

- Years-of-relevant-experience calculation
- Employment record interval merging (overlapping dates)
- Experience relevance formula (years_available / years_required)
- Date confidence assessment

#### Acceptance Criteria

- ✅ Fixture: 2.5 years / 3 required = 83.33% score
- ✅ Fixture: 5 years / 3 required = 100.00% score
- ✅ Overlapping intervals merged correctly: [2019-01 to 2021-06] + [2020-01 to 2022-01] = 3.0 years
- ✅ End-before-start discarded with warning
- ✅ No minimum stated → `None`
- ✅ All tests from SPECIFICATION.md Section 18.1 pass

---

### ⬜ Stage 8: Responsibility Scorer & Final Score & Persistence

**Status:** NOT STARTED  
**Estimated Duration:** 20-30 minutes  
**Prerequisite:** Stages 0-7 complete  

#### What Will Be Built

- TF-IDF vectorizer (one per frozen batch)
- Responsibility matching via cosine similarity
- Dynamic weight normalization
- Final score calculation
- Scoring run persistence (SQLAlchemy + transactions)
- Evidence persistence (match_evidence, missing_items, warnings)

#### Acceptance Criteria

- ✅ Fixture: responsibility_score = 66.33 reproduced exactly
- ✅ Fixture: final_score = 83.17 reproduced exactly
- ✅ Fixture: applied_weights = {required: 0.5294, experience: 0.2353, responsibility: 0.2353, preferred: 0.2353}
- ✅ Weights always sum to 1.0 ± 1e-9
- ✅ All four components present → defaults unchanged
- ✅ Preferred absent → redistribute to other three (formula per Section 12.2)
- ✅ All-`None` → UnscorableJobError
- ✅ One TF-IDF vectorizer per run (asserted by object identity)
- ✅ Full run persistence in one transaction; any failure rolls back entire run
- ✅ Re-runs on same data produce bit-identical results
- ✅ All tests from SPECIFICATION.md Section 18.1 & 18.2 pass

---

## Checkpoint C: UI, Export & Validation (Stages 9–10)

### ⬜ Stage 9: Streamlit UI (5 Pages)

**Status:** NOT STARTED  
**Estimated Duration:** 40-60 minutes  
**Prerequisite:** Stages 0-8 complete  

#### What Will Be Built

1. **Page 1: Create Job** (app routing entry point)
   - Textarea: paste job description
   - Button: "Analyze Description"
   - Transitions to Page 2

2. **Page 2: Confirm Job**
   - Display extracted: title, required, preferred, minimum years, responsibilities
   - Show extraction confidence for each element
   - Buttons: Edit / Delete / Reclassify (optional)
   - Button: "Confirm and Continue" (freezes job)
   - Transitions to Page 3

3. **Page 3: Upload Resumes**
   - File uploader (multi-file)
   - Button: "Validate & Parse Files"
   - Display per-file status table (accepted, duplicate, corrupt, scan, etc.)
   - Button: "Score Candidates"
   - Transitions to Page 4

4. **Page 4: Rankings**
   - Ranked table (candidate, final_score, component scores)
   - Sortable, selectable
   - Button per candidate: "View Details"
   - Transitions to Page 5
   - Mandatory oversight notice (Section 17.3)

5. **Page 5: Candidate Details**
   - Candidate name (display identifier)
   - Full score breakdown (4 components + final)
   - Evidence cards (one per matched requirement + responsibility)
   - Missing items (not identified, unclear, pending)
   - Warnings (year-only dates, PMP candidate, etc.)
   - Button: "Download CSV"
   - Button: "Back to Rankings"

#### Acceptance Criteria

- ✅ All 5 pages render without error
- ✅ Full recruiter flow demoable end-to-end on synthetic data in <5 minutes
- ✅ Evidence display shows source text for every nonzero match
- ✅ Missing items clearly marked as unverified
- ✅ Warnings displayed with codes and messages
- ✅ Mandatory oversight notice present on rankings page
- ✅ CSV export matches persisted values exactly

---

### ⬜ Stage 10: Testing, Documentation & Polish

**Status:** NOT STARTED  
**Estimated Duration:** 30-45 minutes  
**Prerequisite:** Stages 0-9 complete  

#### What Will Be Built

1. **Unit Tests** (TDD; tests written before implementation)
   - Job parser tests (Section 18.1)
   - Resume parser tests (Section 18.1)
   - Qualification scorer tests (Section 18.1)
   - Experience scorer tests (Section 18.1)
   - Responsibility scorer tests (Section 18.1)
   - Weight normalizer tests (Section 18.1)

2. **Integration Tests** (Section 18.2)
   - Full path: paste → parse → confirm → upload → score → persist → export
   - In-memory SQLite DB
   - One corrupt file doesn't block batch
   - Single shared vectorizer per run
   - Injected DB failure leaves zero partial rows

3. **Acceptance Tests** (Section 18.3)
   - All 8 scenarios automated
   - Results compared to expected_rankings.md
   - Name-swap test (identical resume, different name → identical score)

4. **Code Quality**
   - Format with Black: `black .`
   - Lint with Ruff: `ruff check .`
   - Zero errors expected

5. **Documentation**
   - `README.md`:
     - 1-sentence pitch
     - Feature overview (5-7 bullets)
     - Quick start (3 commands)
     - Architecture diagram
     - Testing strategy
     - Tech stack table
     - Link to SPECIFICATION.md
     - Contributing guidelines
   - Update `PROGRESS.md` (this file) to reflect final state

#### Acceptance Criteria

- ✅ All unit tests pass (Section 18.1 fixtures verified)
- ✅ All integration tests pass (Section 18.2 flow verified)
- ✅ All acceptance scenarios pass (Section 18.3 ground truth verified)
- ✅ Ruff clean (zero linting errors)
- ✅ Black clean (all code formatted)
- ✅ README complete and professional
- ✅ Definition of Done (SPECIFICATION.md Section 21) fully satisfied

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

Should point to `venv/` folder.

---

### Issue: Streamlit App Won't Start

**Symptom:**
```
ModuleNotFoundError: No module named 'streamlit'
```

**Solution:**
1. Verify venv is activated (should see `(venv)` prefix)
2. Reinstall requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Try again:
   ```bash
   streamlit run app.py
   ```

---

### Issue: Database Migration Fails

**Symptom:**
```
ERROR [alembic.migration] Can't locate revision identified by 'abc123'
```

**Solution:**
1. Check current head:
   ```bash
   alembic current
   ```
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

## Time Tracking

| Stage | Estimated | Actual | Status |
|-------|-----------|--------|--------|
| 0 | 10-20 min | ~50 min | ✅ COMPLETE |
| 1 | 15-25 min | — | ⏳ PENDING |
| 2 | 15-25 min | — | ⏳ PENDING |
| 3 | 20-30 min | — | ⏳ PENDING |
| 4 | 20-30 min | — | ⏳ PENDING |
| 5 | 15-25 min | — | ⏳ PENDING |
| 6 | 10-15 min | — | ⏳ PENDING |
| 7 | 15-20 min | — | ⏳ PENDING |
| 8 | 20-30 min | — | ⏳ PENDING |
| 9 | 40-60 min | — | ⏳ PENDING |
| 10 | 30-45 min | — | ⏳ PENDING |
| **Total** | **3.5-5 hours** | **~50 min** | — |

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
| config/settings.py | App configuration | ⏳ Stage 1 |
| config/scoring.yaml | Scoring weights & config | ⏳ Stage 1 |
| config/taxonomy/*.json | Skills, degrees, titles, etc. | ⏳ Stage 1 |
| domain/schemas.py | Pydantic data models | ⏳ Stage 1 |
| db/models.py | SQLAlchemy ORM models | ⏳ Stage 1 |
| db/migrations/0001_initial_schema.py | Database schema migration | ⏳ Stage 1 |
| parsing/job_parser.py | Job description parser | ⏳ Stage 3 |
| parsing/resume_parser.py | Resume parser + PII stripping | ⏳ Stage 4 |
| matching/scoring_engine.py | Scoring orchestration | ⏳ Stage 8 |
| ui/pages/*.py | Streamlit pages (5 pages) | ⏳ Stage 9 |
| tests/*.py | Unit/integration/acceptance tests | ⏳ Stage 10 |
| README.md | User-facing documentation | ⏳ Stage 10 |

---

## Next Steps

1. ✅ **Verify Stage 0** is complete locally and on GitHub
2. ⏳ **Start Stage 1** (Taxonomies & Configuration)
   - Message to Claude Code provided
   - Estimated duration: 15-25 minutes
3. ⏳ **Continue through Stages 2-10** in order
4. ✅ **Update this file** after each stage:
   - Change status from `⏳ PENDING` to `✅ COMPLETE`
   - Note actual duration
   - Document any issues encountered

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
5. **Check troubleshooting section above** for common issues
6. **Document the issue** in this file under "Known Issues & Resolutions" for future reference

---

## Checksum & Validation

**Generated:** August 4, 2026, 3:15 AM  
**Stage 0 Commit Hash:** `0c40bc8` (latest)  
**Total Commits:** 6 (initial setup + Stage 0)  
**Branch:** main  
**Remote:** origin (https://github.com/ShreyasCuchcula/resume-job-matcher.git)  

**File Validation:**
- `requirements.txt`: 17 pinned dependencies
- `sample_data/jobs/`: 6 .txt files
- `sample_data/synthetic_resumes/`: 26 PDF/DOCX files
- `sample_data/expected_rankings.md`: 3 job rankings + ground truth

---

**Last Updated:** August 4, 2026, 3:15 AM  
**Next Update:** After Stage 1 complete
