# Resume-Job-Matcher: Project Progress Tracker

**Status:** In Development  
**Current Checkpoint:** B Complete (Stages 0-8 Complete)

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

### ✅ Stage 6: Education Validator

**Status:** COMPLETE

#### What Was Built

Stage 5 already built the complete Section 11 qualification-matching engine, and SPECIFICATION.md Section 11 is explicit that education is *not* a separate scoring component - it's "a qualification item inside required/preferred" scored through the exact same `match_qualifications()`/`ComponentResult` machinery as skills and certifications. So `match_education()`, the degree-level x field formula, the "degree or equivalent experience" clause, and the shared `score = 100 x sum(importance_i x match_i) / sum(importance_i)` formula were all already implemented, tested, and committed in Stage 5 - there was no new production code this stage's spec called for that didn't already exist.

What this stage added was dedicated, explicitly-labeled test coverage proving every Stage 6 acceptance criterion holds through the *public* `match_qualifications()` contract (not just the internal `match_education()` helper Stage 5's own tests already exercise directly):

1. **`tests/unit/test_education_validator.py`** - Section 11.3 math (degree level x field, one-level-below=0.50, somewhat-related=0.75, level-only, field-only) run through `match_qualifications()` with education-only requirement lists; the "empty category -> `None`" vs. "required but candidate has nothing -> a real 0.0 with a `MissingItem`" distinction made explicit; the "degree or equivalent experience" formula's `max()`/never-invent-years behavior; and the Section 11.5 preferred-quals fixture (72.00) reproduced again through this stage's own test surface, since that's the only 72.00 fixture SPECIFICATION.md actually defines (it isn't education-specific in the source material - documented in the test module's own docstring rather than silently fabricating a fake education-only fixture number that doesn't exist in the spec).
2. **`tests/integration/test_education_validator_integration.py`** - confirms exactly one of the 6 real job descriptions (`job_05_data_scientist.txt`) declares "or equivalent experience," and drives Harper Nakamura's real no-degree resume through the actual `matching.scoring_engine.score_required_qualifications()` entry point (not the bare matching function) with and without a supplied `relevant_years`, proving the exact seam Stage 7's experience scorer will plug into already works end to end.

#### Known Issues & Resolutions

1. **`expected_rankings.md`'s hand-reasoned claim that Harper Nakamura's "required score reaches 100.00 purely through the equivalence clause"** doesn't hold exactly against the real parser output (97.5, not 100.00) - one of the *other* required skill items isn't a perfect 1.00 match for this candidate. This isn't a bug: `expected_rankings.md` explicitly caveats itself ("the real job parser may assign different importance... exact scores will shift even though the ordering and reasoning below should still hold"). The integration test was written to assert what must hold exactly - the education item itself carries zero `MissingItem`s and full 1.00 adjusted strength via the equivalence clause - rather than a whole-category total that depends on unrelated items' real extraction quality.

#### Verification

423 tests total, all passing; `ruff check .` clean. All Stage 5 acceptance criteria this stage re-verifies (94.29/72.00 fixtures, degree level x field math, empty-category `None`, degree-or-equivalent contract) still hold; the two new Stage 6 test modules add 22 additional tests specifically proving those same guarantees survive the public `match_qualifications()`/`score_required_qualifications()` contracts rather than only the internal helpers.

---

### ✅ Stage 7: Experience Scorer

**Status:** COMPLETE

#### What Was Built

1. **`matching/experience_scorer.py`** - the full Section 13 experience component:
   - `merge_intervals()` (Section 13.3) - sorts by start date and coalesces overlapping/touching intervals so parallel roles never double-count calendar time; a merged interval's `date_confidence` is the minimum across everything that fed into it.
   - `is_title_relevant()` / `is_similarity_relevant()` / `determine_role_relevance()` (Section 13.2) - "a role counts if either passes": normalized title matches the job's own title or one of its `related_titles` (titles.json), or mean bullet/responsibility cosine similarity clears the configured threshold via an optional fitted vectorizer. **This is load-bearing, not a nice-to-have**: without it, an unrelated role's tenure would silently inflate "relevant experience" - `sample_data/expected_rankings.md`'s Elliot Marsh fixture (a reporting-analyst role must contribute zero years toward a Data Scientist posting) depends on it directly.
   - `calculate_relevant_years()` - determines role-relevant intervals, merges them, sums to years; excludes any employment record with unparseable dates (using the *scoring run's* `run_date` to resolve "Present" roles, not whatever run_date the resume happened to be parsed with) with a `MISSING_DATES` warning; adds `TITLE_ONLY_RELEVANCE` when the job has a stated minimum but zero responsibilities to compare bullets against.
   - `experience_score_from_years()` / `calculate_experience_match()` (Section 13.1/13.4) - `score = 100 * min(relevant_years / required_years, 1.0)`, rounded to 2dp; `score=None` when the job states no explicit minimum (never inferred from a seniority word); a real `0.00` (not `None`) when the minimum exists but zero relevant years were found.
2. **`matching/scoring_engine.py`** - `score_experience()` and `compute_relevant_years()`, both hard-asserting `job.confirmed`. `compute_relevant_years()` is computed independently of whether the job states a general experience minimum, since a per-requirement "degree or equivalent experience" clause (Section 11.3, Stage 5/6) is orthogonal to `job.minimum_relevant_years` - its output feeds directly into `score_required_qualifications(relevant_years=...)`, the exact seam Stage 5/6 built ahead of time for this stage to plug into.

The similarity path (Section 13.2 path 2) needs a fitted `TfidfVectorizer`, a batch-level artifact Section 12.3 says is fit once per scoring run - that doesn't exist until Stage 8. `vectorizer` is an optional parameter throughout (default `None`): title match always works standalone now; Stage 8 can pass its fitted vectorizer in later to also exercise the similarity path, with zero signature changes.

#### Known Issues & Resolutions

1. **The user's own Stage 7 spec message never mentioned role relevance, title matching, or `related_titles` at all** - it described interval merging over "employment records" generically. Implementing that literally (summing every employment record's tenure regardless of relevance) would have silently broken an already-committed acceptance fixture: `expected_rankings.md`'s Elliot Marsh scenario explicitly requires an unrelated reporting-analyst role to contribute zero years toward a Data Scientist posting's experience score. Resolved by implementing full Section 13.2 role relevance (title-match path fully working now; the similarity path wired as an optional forward-compatible parameter for Stage 8), verified directly against the real Elliot Marsh resume and job.
2. **The Section 18.1 fixtures (2.5/3 -> 83.33, 5/3 -> 100.00) can't be reproduced exactly through real calendar dates** - leap years mean no real date range divides to exactly `2.5 * 365.25` days. Resolved by extracting the pure formula into `experience_score_from_years(relevant_years, required_years)`, tested directly against the exact fixture values, with a separate real-dates test proving the full pipeline lands in the right ballpark (not exact-fixture) through actual employment intervals.
3. **`EmploymentRecord` has no field distinguishing *why* its dates are unparseable** (`MISSING_DATES` vs. `INVALID_DATE_RANGE` both collapse to `start_date=None, end_date=None, date_confidence=0.0` at Stage 4 parse time, with no residual marker). Rather than fabricate a false distinction at scoring time, excluded records are summarized under one `MISSING_DATES` scoring warning ("may be underestimated"), matching Section 13.4's own umbrella phrasing for this exact case.

#### Verification

476 tests total, all passing; `ruff check .` clean. Both Section 18.1 formula fixtures (83.33, 100.00) reproduce exactly via the pure formula function. Integration-tested against every real job description scored against every real parseable synthetic resume (no crashes, every score in [0,100]) plus every named `expected_rankings.md` scenario touching this component: Peyton Marsh's year-only dates clearing the minimum with lowered confidence surfaced on the evidence (not discounting the score); Skyler Vance's undated role excluded entirely with a `MISSING_DATES` warning; Elliot Marsh's unrelated role correctly contributing zero years (role relevance, not a mere discount); Harper Nakamura's real employment history producing the documented ~7 relevant years from actual parsed dates, then flowing straight into the Section 11.3 degree-or-equivalent formula; Jordan Ellis clearing Job 1's minimum; and Job 4's stated absence of an experience minimum yielding `experience_score=None` for every candidate.

---

## Pre-Stage 9 Infrastructure: Company & Job Lifecycle

**Status:** COMPLETE

**Not one of the 10 numbered stages.** A focused database/service-layer expansion requested and confirmed explicitly by the project owner as a deliberate scope addition ahead of Stage 9, documented as a deviation in `SPECIFICATION.md` Section 6.3 rather than folded silently into the existing spec. Does not touch `parsing/` or `matching/` - every Stage 3-7 test still passes unchanged.

#### What Was Built

1. **`domain/enums.py` / `domain/schemas.py`** - `JobStatus` enum; a new `Company` model; `JobProfile` gains `company_id` / `status` / `expires_at`, all defaulted so every existing caller is unaffected.
2. **Migrations `0003` and `0004`** (`db/migrations/versions/`) - `0003` adds the `companies` table and `jobs.company_id` / `status` / `expires_at`; `0004` makes `jobs.parser_version` nullable, mirroring `resumes.parser_version`'s existing nullable-until-parsed pattern from migration `0002`, since job creation now happens before parsing (see `services/job_service.py` below). Verified with a real `alembic upgrade head` / `downgrade -1` round-trip against a scratch SQLite database (schema inspected via `PRAGMA` before and after), plus the new DDL compiled cleanly against the PostgreSQL dialect (no live Postgres server available in this environment).
3. **`db/models.py`** - `Company` ORM model with a cascading relationship to `Job`; `Job` gains the three new columns plus a `CHECK` constraint on `status` matching every other enum-like column's existing convention in this file.
4. **`db/repositories.py`** - created for the first time (documented in the project's file layout since the start but never built, since no earlier stage needed job-level DB persistence): `get_company_by_id`, `get_jobs_by_company`, `create_company`.
5. **`services/job_service.py`** - created for the first time (same situation as `db/repositories.py`): `create_job` (requires an existing `company_id`), `parse_and_persist_job`, `confirm_job`, `update_job_status`. `invalidate` is deliberately not implemented - it depends on `scoring_runs` persistence, which doesn't exist until Stage 8.

#### Known Issues & Resolutions

1. **The request that kicked off this work asked me not to verify it against the authoritative specification, and referenced a `services/job_service.py` file to "modify" that did not exist in the repository.** Paused before making any changes, checked both claims directly against the repo and against `SPECIFICATION.md` (no company/job-lifecycle concept exists anywhere in the spec; `services/` contained only `candidate_service.py`), and surfaced the discrepancy before proceeding rather than executing silently. Confirmed explicitly as genuinely wanted, with the fix being: document the deviation in the spec instead of hiding it, build the referenced file for real instead of assuming it existed, and verify normally instead of skipping it.
2. **A previously-unnoticed bug surfaced by testing the new cascade relationship**: SQLite ships `PRAGMA foreign_keys` OFF per connection by default, so every `ON DELETE CASCADE` / `ON DELETE SET NULL` constraint declared anywhere in `db/models.py` - not just the new `companies` one - has been silently a no-op on SQLite since Stage 1; deleting a parent row left every child row orphaned instead of cascading. Fixed once, globally, in `db/base.py` via a SQLAlchemy connect-event listener scoped to real `sqlite3.Connection` objects only (PostgreSQL is unaffected). Full suite re-verified green after the fix; nothing depended on the previously-broken behavior.
3. **`jobs.parser_version` was `NOT NULL`, but `create_job()` must persist a row before parsing has run.** Rather than write a fake placeholder version string, added migration `0004` to make it nullable - the identical fix already established for `resumes.parser_version` in migration `0002`, for the identical reason.

#### Verification

508 tests total, all passing; `ruff check .` clean. Every Stage 3-7 test unchanged and still green. Migration chain `0001` through `0004` round-trips cleanly on SQLite; new DDL compiles cleanly against the PostgreSQL dialect.

---

### ✅ Stage 8: Responsibility Scorer & Final Score & Persistence

**Status:** COMPLETE — Checkpoint B complete (Stages 3-8 done)

#### What Was Built

1. **`matching/responsibility_scorer.py`** (Section 12) - Section 12.3's exact `TfidfVectorizer` configuration (unfitted - the batch-level fit happens once, in `services/scoring_service.py`); per-responsibility best-bullet selection via cosine similarity with the 0.20 weak-match threshold; no responsibilities → inapplicable (`None`); responsibilities present but zero candidate bullets → a real `0.0` + `NO_EVIDENCE_BULLETS` warning. Every responsibility always lands in `evidence` (never `missing` - `MissingItem.requirement_id` has no responsibility-shaped analog). The pure formula is isolated into `responsibility_score_from_adjusted()` so the Section 12.5 fixture (bests 0.76/0.65/0.58 → 66.33) reproduces exactly.
2. **`matching/weight_normalizer.py`** (Section 13.5) - `normalize_weights()`: inapplicable (`None`) components redistribute their weight; a real `0.0` keeps its weight; raises `UnscorableJobError` when every component is inapplicable.
3. **`matching/scoring_engine.py`** extended with Section 14.1's full orchestration: `ScoringContext` (one fitted vectorizer + taxonomy + thresholds + weights + run date + version strings, shared by every candidate in a run), `assert_job_is_scorable()` (the `UnscorableJobError` check, done once per job rather than once per candidate, since every component's applicability depends only on the job's own fields), `final_score_from_components()`, `score_candidate()` (all four components → one `MatchResult`), and `rank_match_results()` (Section 13.6 tie-break: final↓, required↓, responsibility↓, display_identifier↑).
4. **`services/scoring_service.py`** (Section 14.2) - `run_scoring_batch()`: raises `UnscorableJobError` before touching the database if the job can never be scored; fits exactly one `TfidfVectorizer` on the full batch corpus (every job responsibility + every candidate's evidence bullets) and reuses that instance for every candidate; persists `scoring_runs` + every candidate's `match_results`/`match_evidence`/`missing_items`/`scoring_warnings` in a single transaction, rolling back everything on any failure.

#### Known Issues & Resolutions

1. **The Section 13.6 worked fixture (83.17) contradicts the spec's own inline formula comment.** `final = Σ(component_score × normalized_weight)  # rounded to 2 dp` reads as a single rounding step after summing - but `94.29×0.45 + 83.33×0.20 + 66.33×0.20 + 72.00×0.15` sums to `83.1625`, which rounds to `83.16`, not `83.17`. Verified directly in Python (not just by hand) that only rounding each component's weighted contribution to 2dp *before* summing reproduces `83.17` exactly. Implemented the per-term-rounding interpretation, since the ACCEPTANCE CRITERIA explicitly demanded the fixture reproduce "to the digit" - documented the discrepancy directly in `final_score_from_components()`'s docstring and in a dedicated test that computes both interpretations side by side.
2. **`MissingItem.requirement_id` is a non-nullable UUID with no responsibility-shaped equivalent**, so a job responsibility with zero matching evidence can't be represented as a "missing" item the way an unmet skill/education/certification requirement can. Resolved per `MatchEvidence.requirement_id`'s own schema comment ("None for responsibility matches"): every responsibility always produces a `MatchEvidence` entry (with `adjusted_strength=0.0` and an explicit no-match placeholder when there are literally no bullets to compare against), never a `MissingItem`.
3. **Persisting `match_evidence`/`missing_items` rows for the first time in this project surfaced real foreign-key requirements**: `job.job_id` and every `JobRequirement.requirement_id`/`JobResponsibility.responsibility_id` must match already-persisted rows (not a freshly re-parsed `JobProfile` with new random UUIDs), and this is now genuinely enforced at the SQLite level thanks to the pre-Stage-9 FK-pragma fix. Documented explicitly as a caller contract in `scoring_service.py`'s module docstring; a full "reconstruct `JobProfile`/`CandidateProfile` from persisted rows" loader is Stage 9 UI-wiring territory, not built here - integration tests build a test-local equivalent to exercise the real persistence path with valid FKs.

#### Verification

553 tests total, all passing; `ruff check .` clean. Both Section 18.1 fixtures this stage covers reproduce exactly (66.33 responsibility, 83.17 final). The Section 13.5 weight-redistribution fixture (preferred absent → 0.5294/0.2353/0.2353) reproduces exactly, alongside experience-absent and responsibility-absent redistribution and the all-`None` → `UnscorableJobError` case. `services/scoring_service.py` verified against the real in-memory SQLite `db_session` fixture with real job/resume data: one vectorizer built per batch regardless of candidate count (spied, not assumed), a simulated DB failure mid-batch leaves zero `scoring_runs`/`match_results`/`match_evidence` rows, and every persisted row's foreign keys are real (FK enforcement genuinely active). Full-pipeline integration tests run every real job against every real parseable resume (no crashes, every final score in `[0,100]`, weights always sum to 1.0) plus targeted acceptance coverage against `expected_rankings.md`: Job 1's five-candidate ranking order matches exactly via the real tie-break-capable ranking function; Job 2's absent preferred section and Job 4's absent experience minimum both correctly redistribute weight; and the Section 9.4 name-swap invariant now holds all the way through the final weighted score, not just individual components.

**Checkpoint B (Stages 3-8, "Parsers & Scoring Brain") is complete**: job and resume parsing, all four scoring components, dynamic weight normalization, the final score formula, and full transactional persistence all work together end to end against real synthetic data.

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
| 6 | Education Validator | ✅ COMPLETE |
| 7 | Experience Scorer | ✅ COMPLETE |
| 8 | Responsibility Scorer, Final Score & Persistence | ✅ COMPLETE |
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
| db/migrations/versions/0003_*.py | Companies table + job lifecycle fields (pre-Stage-9) | ✅ Ready |
| db/migrations/versions/0004_*.py | Nullable jobs.parser_version (pre-Stage-9) | ✅ Ready |
| db/repositories.py | Company query/persist helpers (pre-Stage-9) | ✅ Ready |
| ingestion/*.py | File validation, PDF/DOCX extraction, hashing | ✅ Ready |
| services/candidate_service.py | Batch ingestion orchestration | ✅ Ready |
| services/job_service.py | Job create/parse/confirm/status persistence (pre-Stage-9) | ✅ Ready |
| parsing/job_parser.py | Job description parser | ✅ Ready |
| parsing/section_detector.py, skill_extractor.py, education_extractor.py, certification_extractor.py, requirement_extractor.py, responsibility_extractor.py, common.py | Job parser support modules | ✅ Ready |
| parsing/resume_parser.py | Resume parser + PII stripping | ✅ Ready |
| parsing/pii.py, employment_extractor.py, normalization/dates.py, normalization/titles.py | Resume parser support modules | ✅ Ready |
| matching/qualification_matcher.py | Skill/education/certification matching + scoring formula | ✅ Ready |
| matching/experience_scorer.py | Relevant-years calculation + experience component (Section 13) | ✅ Ready |
| matching/responsibility_scorer.py | TF-IDF/cosine responsibility similarity (Section 12) | ✅ Ready |
| matching/weight_normalizer.py | Dynamic weight redistribution (Section 13.5) | ✅ Ready |
| matching/scoring_engine.py | Full per-candidate orchestration: all 4 components + final score + ranking | ✅ Ready |
| services/scoring_service.py | Batch scoring run orchestration + transactional persistence (Section 14.2) | ✅ Ready |
| ui/pages/*.py | Streamlit pages (5 pages) | ⬜ Stage 9 |
| README.md | User-facing documentation | ⬜ Stage 10 |

---

## Next Steps

1. ✅ Stages 0-8 complete and verified, locally and on GitHub - **Checkpoint B complete**
2. ✅ Pre-Stage-9 Company/job-lifecycle infrastructure complete and verified (see dedicated section above) - not a numbered stage
3. ⬜ **Start Stage 9** (Streamlit UI, 5 pages)
4. ⬜ Continue through Stage 10
5. Update this file after each stage: flip status to `✅ COMPLETE`, document any issues encountered, keep the Stage Completion Status table current

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

**Latest commit:** `f9a724a` - "Verify full scoring pipeline against real data and ground truth (Stage 8)"  
**Total commits:** 56  
**Branch:** main  
**Remote:** origin (https://github.com/ShreyasCuchcula/resume-job-matcher.git)

**File validation:**
- `requirements.txt`: 16 pinned dependencies
- `sample_data/jobs/`: 6 `.txt` files
- `sample_data/synthetic_resumes/`: 26 PDF/DOCX files
- `sample_data/expected_rankings.md`: ground truth for 3 jobs + full ingestion-status table
- `config/taxonomy/`: 178 skills, 5 degree levels, 13 fields, 26 certifications, 26 titles, 35 phrase mappings
- `db/models.py`: 14 ORM tables (13 from Section 6.1 + `companies`, pre-Stage-9), 4 migrations applied
- `parsing/`: job description parser (Section 10) and resume parser (Section 9) both complete, across 12 modules
- `normalization/`: dates.py, titles.py
- `matching/`: qualification_matcher.py, experience_scorer.py, responsibility_scorer.py, weight_normalizer.py, scoring_engine.py - all four Section 11-13 scoring components plus full Section 14.1 per-candidate orchestration and ranking
- `services/`: candidate_service.py, job_service.py, scoring_service.py - ingestion, job persistence, and full transactional batch-scoring orchestration (Section 14.2)
- `db/repositories.py`: pre-Stage-9 Company persistence helpers
- `tests/`: 553 tests passing (unit + integration)
