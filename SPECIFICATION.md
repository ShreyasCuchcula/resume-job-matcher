# Explainable Resume–Job Matcher — Complete Functional & Technical Specification

**Document version:** 1.0
**Status:** Approved baseline for implementation
**Source:** Consolidates the original MVP Technical Blueprint plus all implementation decisions agreed during project planning. Where this document is more specific than the blueprint, this document governs. Where the blueprint prohibits something, the prohibition stands.

---

## 0. How to read this document

This is the single source of truth for building the MVP. It is organized so that:

- Sections 1–2 define **what** the product does and does not do.
- Sections 3–6 define the **technical foundation** (stack, structure, configuration, data model).
- Sections 7–10 define the **processing logic** (ingestion, parsing, normalization).
- Sections 11–13 define the **scoring mathematics** exactly, with worked numbers that double as test fixtures.
- Sections 14–16 define the **application behavior** (orchestration, UI, export).
- Sections 17–19 define **error handling, privacy, and responsible use**.
- Sections 20–23 define **testing, synthetic data, delivery plan, and completion criteria**.

Every rule in this document is implementable as written. Nothing requires an external API, an LLM, or paid services.

---

## 1. Product definition

### 1.1 Purpose

A recruiter decision-support application. A recruiter pastes one job description, uploads multiple text-based resumes (PDF/DOCX), and receives a ranked list of candidates with a fully explainable, evidence-backed score for each. Every point of every score must be traceable to visible resume text.

### 1.2 Core principles (non-negotiable invariants)

1. **Decision support, never decision making.** The tool ranks and explains; it never hires, rejects, or filters candidates automatically.
2. **Absence of evidence is not evidence of absence.** "Not identified in the resume" is always presented as unverified, never as proof the candidate lacks something.
3. **Total explainability.** Every nonzero match must display its supporting resume text. A score without evidence is a bug.
4. **Fairness by exclusion.** Names, contact details, age, graduation years, gender, race, religion, disability, marital status, photographs, and other protected attributes never enter the scoring pipeline.
5. **Determinism and reproducibility.** Identical inputs + identical versions (parser, scorer, taxonomy, config) always produce identical outputs, including candidate identifiers and rankings.

### 1.3 Primary user flow

1. Recruiter pastes a job description (title optional) → clicks **Analyze Description**.
2. System parses it into: title, required qualifications, preferred qualifications, minimum relevant years, responsibilities — each with original source text and an extraction-confidence value.
3. Recruiter reviews the extracted profile on a confirmation page. Editing (add / edit / delete / reclassify required↔preferred) is optional; clicking **Confirm and Continue** is mandatory. Confirmation freezes the job profile.
4. Recruiter uploads one or more resumes (.pdf / .docx, text-based, ≤10 MB each).
5. System validates and parses each file, reporting per-file status: accepted, duplicate, unsupported, corrupt, probable scan, or parsed-with-warnings. One bad file never blocks the rest.
6. Recruiter clicks **Score Candidates**. The system freezes the batch, fits one TF-IDF vectorizer for the batch, scores every candidate, and persists everything in a scoring run.
7. Recruiter views the ranked table, opens any candidate for the full score breakdown with evidence, and downloads a CSV export.

### 1.4 Explicit non-goals (MVP will NOT)

- Make or suggest hiring decisions, or auto-reject anyone.
- OCR scanned/image resumes (they are detected and rejected with a clear message).
- Scrape job boards, integrate with ATS systems, or call any external/LLM API.
- Train neural networks or learn from recruiter behavior.
- Use protected personal information in scoring.
- Provide authentication, roles, or enterprise access control.

---

## 2. System architecture

### 2.1 Component diagram

```text
                 ┌──────────────────────┐
 Job description │      Job Parser       │──► Structured Job Profile ──► Recruiter
 (pasted text)──►│ (sections, cues,      │        (with confidence)      Confirmation
                 │  confidence)          │                                   │ freeze
                 └──────────────────────┘                                   ▼
 Resume files    ┌──────────────────────┐      ┌──────────────────────────────────┐
 (.pdf/.docx) ──►│  Ingestion +          │      │        Scoring Run (frozen)       │
                 │  Validation           │      │  1. fit ONE TF-IDF vectorizer     │
                 └─────────┬────────────┘      │  2. responsibility scores          │
                           ▼                    │  3. experience relevance + score  │
                 ┌──────────────────────┐      │  4. qualification scores           │
                 │  Resume Parser        │─────►│  5. dynamic weights → final       │
                 │  (sections, evidence, │      └───────────────┬──────────────────┘
                 │   PII stripping)      │                      ▼
                 └──────────────────────┘         Ranked Results + Evidence
                                                              │
                                          ┌───────────────────┴───────────────┐
                                          ▼                                   ▼
                                 Streamlit Dashboard                 SQLAlchemy → DB
                                 (5 pages + export)             (SQLite dev / PostgreSQL)
```

### 2.2 Application layers

| Layer | Responsibility | Key modules |
|---|---|---|
| Interface | Job entry, confirmation, uploads, rankings, detail, export | `ui/` |
| Services | Use-case orchestration between UI and everything else | `services/` |
| Parsing | Text → structured sections, requirements, evidence | `parsing/` |
| Normalization | Aliases, titles, degrees, dates, phrases → canonical forms | `normalization/` |
| Matching & Scoring | Requirement↔evidence matching, four components, weights | `matching/` |
| Ingestion | File validation, extraction, hashing, storage | `ingestion/` |
| Persistence | Models, repositories, migrations, transactions | `db/` |
| Domain | Pydantic schemas, enums, exceptions shared by all layers | `domain/` |
| Configuration | Settings, scoring config, taxonomies | `config/` |

**Dependency rule:** `ui → services → (parsing | matching | ingestion) → normalization → domain`. The `db` layer is called only by `services`. Nothing imports from `ui`. Scoring code never touches Streamlit or the database directly — this keeps every scorer unit-testable in isolation.

### 2.3 Mandatory pipeline order within a scoring run

The order below is fixed because experience relevance depends on the fitted vectorizer:

1. Load the confirmed (frozen) job profile.
2. Load all successfully parsed candidate profiles; freeze the candidate set.
3. Assign deterministic display identifiers (Section 14.3).
4. Fit **one** `TfidfVectorizer` on: all confirmed job responsibilities + all evidence bullets of all candidates in the batch.
5. For each candidate: responsibility score → experience score (role relevance may reuse the vectorizer) → required score → preferred score.
6. Normalize weights over applicable components; compute final score.
7. Persist run + all results + all evidence + all warnings in one transaction.
8. Rank from persisted results.

Adding a candidate afterward requires a **new** scoring run (IDF weights would change).

---

## 3. Technology stack and dependencies

### 3.1 Stack with rationale

| Purpose | Technology | Rationale |
|---|---|---|
| Language | Python 3.11+ | Modern typing (`X | None`, `Literal`), strong NLP/data ecosystem |
| UI | Streamlit (multipage) | Fastest path to a functional recruiter dashboard in pure Python |
| Database (dev/test) | SQLite | Zero-setup local development; file-based |
| Database (final MVP) | PostgreSQL 15+ | Blueprint requirement; JSONB, concurrency, growth path |
| ORM | SQLAlchemy 2.x | Engine-agnostic models; one `DATABASE_URL` switches engines |
| Migrations | Alembic | Versioned schema, tested against both engines |
| PDF text | PyMuPDF (`fitz`) | Reliable text-layer extraction |
| DOCX text | python-docx | Paragraphs + tables |
| NLP | spaCy + `en_core_web_sm` | Sentence segmentation, lemmatization, PERSON entities (PII backstop) |
| Rules | Python `re` | Dates, years-of-experience, degrees, headings, cues |
| Vectorization | scikit-learn `TfidfVectorizer` | Explainable baseline; no embeddings in MVP |
| Similarity | scikit-learn `cosine_similarity` | Responsibility ↔ bullet matrix |
| Data/export | pandas | Ranking tables, CSV export |
| Config | YAML + pydantic-settings | Validated, typed configuration; fail-fast on startup |
| Testing | pytest | Unit, integration, acceptance |
| Quality | Ruff + Black | Lint + format (both kept; evaluators may expect both) |
| VCS | Git + GitHub | History, portfolio |

### 3.2 requirements.txt (pinned, verified compatible)

```text
streamlit==1.37.*
pandas==2.2.*
pymupdf==1.24.*
python-docx==1.1.*
spacy==3.7.*
scikit-learn==1.5.*
sqlalchemy==2.0.*
psycopg[binary]==3.2.*
alembic==1.13.*
pydantic==2.8.*
pydantic-settings==2.4.*
pyyaml==6.0.*
python-dateutil==2.9.*
pytest==8.3.*
ruff==0.5.*
black==24.*
```

Post-install step (documented in README and automated in a `make setup` / `setup.sh`):

```bash
python -m spacy download en_core_web_sm
```

### 3.3 Database strategy (final decision)

- Default `DATABASE_URL=sqlite:///./resume_matcher.db` in `.env.example` → the app runs immediately after `pip install`.
- All models use portable types: UUIDs stored as `CHAR(36)` on SQLite / native `UUID` on Postgres via a custom `GUID` TypeDecorator; JSON via SQLAlchemy `JSON` (maps to `JSONB` on Postgres).
- `docker-compose.yml` ships with a ready Postgres 16 service; switching = change one env line, run `alembic upgrade head`.
- CI-style test run executes the full test suite against SQLite; a smoke migration test targets Postgres when available.
- Raw resume files are **never** stored in the database. Files live in `uploads/` (git-ignored) under server-generated names `{sha256}.{ext}`; the DB stores path + hash + metadata.

---

## 4. Project structure

```text
resume_job_matcher/
├── app.py                      # Streamlit entry point + navigation
├── requirements.txt
├── pyproject.toml              # ruff/black/pytest config
├── alembic.ini
├── docker-compose.yml          # optional Postgres
├── setup.sh                    # venv + deps + spacy model + migrate
├── README.md
├── .env.example                # DATABASE_URL, UPLOAD_DIR, etc.
├── .gitignore                  # uploads/, .env, *.db, __pycache__, real resumes
├── config/
│   ├── settings.py             # pydantic-settings: env + yaml loading + validation
│   ├── scoring.yaml            # weights, thresholds, limits (Section 6.2)
│   └── taxonomy/
│       ├── skills.json         # ~150–200 skills: aliases, category, related_skills
│       ├── degrees.json        # level ladder + degree aliases
│       ├── fields.json         # field-of-study relatedness map (1.00/0.75 tiers)
│       ├── certifications.json # ~25 certs/licenses: aliases, equivalents
│       ├── titles.json         # canonical titles + related-title lists
│       ├── phrase_normalization.json
│       └── VERSION             # taxonomy_version string, e.g. "tax-1.0"
├── db/
│   ├── base.py                 # DeclarativeBase, GUID TypeDecorator
│   ├── session.py              # engine + session factory from settings
│   ├── models.py               # all ORM models (Section 6)
│   ├── repositories.py         # typed query/persist functions per aggregate
│   └── migrations/             # alembic env + versions
├── domain/
│   ├── enums.py                # RequirementType, EvidenceSection, RunStatus, ...
│   ├── schemas.py              # all pydantic models (Section 5)
│   └── exceptions.py           # UnscorableJobError, ParsingError, ValidationError...
├── ingestion/
│   ├── validation.py           # extension, signature, size, corrupt, scan checks
│   ├── pdf_reader.py
│   ├── docx_reader.py
│   └── hashing.py              # sha256, duplicate detection
├── parsing/
│   ├── common.py               # line/sentence utilities, heading detection helpers
│   ├── section_detector.py     # job + resume heading dictionaries
│   ├── job_parser.py           # orchestrates job extraction
│   ├── resume_parser.py        # orchestrates resume extraction + PII stripping
│   ├── requirement_extractor.py
│   ├── skill_extractor.py      # longest-match-first dictionary matching
│   ├── education_extractor.py
│   ├── certification_extractor.py
│   ├── employment_extractor.py # titles + date ranges
│   ├── responsibility_extractor.py
│   └── pii.py                  # 3-layer PII stripping (Section 9.4)
├── normalization/
│   ├── skills.py
│   ├── qualifications.py
│   ├── titles.py
│   ├── dates.py                # month/year parsing, Present, intervals
│   └── text.py                 # lowercase, whitespace, phrase normalization
├── matching/
│   ├── qualification_matcher.py  # skills + education + certs, required & preferred
│   ├── experience_matcher.py     # relevance, interval merge, years formula
│   ├── responsibility_matcher.py # vectorizer fit, cosine matrix, thresholding
│   ├── scoring_engine.py         # per-candidate orchestration (Section 14)
│   └── weight_normalizer.py
├── services/
│   ├── job_service.py          # create/parse/confirm/invalidate
│   ├── candidate_service.py    # ingest/parse/persist candidates
│   ├── scoring_service.py      # run lifecycle, batch scoring, transaction
│   └── export_service.py       # CSV builder
├── ui/
│   ├── pages/
│   │   ├── 1_create_job.py
│   │   ├── 2_confirm_job.py
│   │   ├── 3_upload_resumes.py
│   │   ├── 4_rankings.py
│   │   └── 5_candidate_details.py
│   └── components/             # evidence card, warning list, score bar, gates
├── tests/
│   ├── conftest.py             # fixtures: profiles, taxonomies, in-memory DB
│   ├── fixtures/               # tiny sample texts + files for tests
│   ├── unit/
│   ├── integration/
│   └── acceptance/
├── sample_data/
│   ├── generate.py             # builds all synthetic files deterministically
│   ├── jobs/                   # 6 synthetic job descriptions (.txt)
│   ├── synthetic_resumes/      # 25+ generated .pdf/.docx incl. broken ones
│   └── expected_rankings.md    # documented ground truth for 3 jobs
└── uploads/                    # runtime storage (git-ignored)
```

---

## 5. Domain schemas (complete)

All inter-module data uses pydantic v2 models defined in `domain/schemas.py`. Parsers never return bare dicts.

```python
# --- enums (domain/enums.py) ---
RequirementType = Literal["skill", "education", "certification", "license"]
EvidenceSection = Literal["skills", "experience", "project", "research",
                          "summary", "education", "certification"]
RunStatus       = Literal["active", "invalidated"]
FileStatus      = Literal["accepted", "duplicate", "unsupported", "corrupt",
                          "probable_scan", "parsed_with_warnings", "failed"]

# --- shared ---
class ParsingWarning(BaseModel):
    code: str            # e.g. "YEAR_ONLY_DATE", "NO_HEADINGS", "PMP_PENDING"
    message: str         # human-readable, shown in UI
    source_text: str | None = None

class ScoringWarning(BaseModel):
    code: str
    message: str
    related_requirement_id: UUID | None = None

# --- job side ---
class JobRequirement(BaseModel):
    requirement_id: UUID
    type: RequirementType
    canonical_name: str
    original_text: str
    importance: int                      # 1 | 2 | 3 (capped at 3)
    confidence: float                    # 0.0–1.0 extraction confidence
    required: bool                       # True=required, False=preferred
    allows_equivalent_experience: bool = False
    equivalent_years: float | None = None   # only if explicitly stated
    degree_level: str | None = None      # education items
    field_of_study: str | None = None    # education items

class JobResponsibility(BaseModel):
    responsibility_id: UUID
    original_text: str
    normalized_text: str
    position: int

class JobProfile(BaseModel):
    job_id: UUID
    title: str | None
    raw_description: str
    required_qualifications: list[JobRequirement]
    preferred_qualifications: list[JobRequirement]
    minimum_relevant_years: float | None
    responsibilities: list[JobResponsibility]
    warnings: list[ParsingWarning]
    parser_version: str
    confirmed: bool = False

# --- candidate side ---
class CandidateQualification(BaseModel):
    type: RequirementType
    canonical_name: str
    original_text: str
    evidence_section: EvidenceSection
    evidence_text: str                   # full sentence/bullet shown to recruiter
    evidence_strength: float             # 1.00/0.90/0.80/0.50/0.00 (Section 11.3)
    extraction_confidence: float

class EducationRecord(BaseModel):
    degree_level: str | None             # ladder key (Section 10.5)
    field_of_study: str | None
    completed: bool | None               # None = unclear
    original_text: str
    # NOTE: graduation year is intentionally absent (age proxy).

class CertificationRecord(BaseModel):
    canonical_name: str
    original_text: str
    held: bool                           # False for candidate/pending/coursework
    pending: bool = False

class EmploymentRecord(BaseModel):
    employment_id: UUID
    original_title: str | None
    normalized_title: str | None
    company: str | None                  # display only, never scored
    start_date: date | None
    end_date: date | None                # None can mean Present (see flag)
    is_current: bool = False
    date_confidence: float               # 1.0 exact, lowered for year-only
    description: str

class EvidenceBullet(BaseModel):
    bullet_id: UUID
    employment_id: UUID | None
    section_type: Literal["employment", "project", "research"]
    original_text: str
    normalized_text: str

class CandidateProfile(BaseModel):
    candidate_id: UUID
    display_identifier: str              # "Candidate 001" — deterministic
    file_hash: str
    raw_resume_text: str                 # post-extraction, pre-PII-strip (stored, not scored)
    scoring_text_available: bool
    skills: list[CandidateQualification]
    education: list[EducationRecord]
    certifications: list[CertificationRecord]
    employment: list[EmploymentRecord]
    evidence_bullets: list[EvidenceBullet]
    warnings: list[ParsingWarning]
    parser_version: str

# --- results ---
class MatchEvidence(BaseModel):
    requirement_id: UUID | None          # None for responsibility matches
    responsibility_id: UUID | None
    matched_canonical: str
    evidence_text: str
    evidence_section: str
    raw_strength: float                  # raw similarity or evidence strength
    adjusted_strength: float             # after thresholds/importance rules

class MissingItem(BaseModel):
    requirement_id: UUID
    canonical_name: str
    status: Literal["not_identified", "unclear", "pending_credential"]
    note: str                            # e.g. "Not identified in the resume —
                                         #      this is not proof of absence."

class ComponentResult(BaseModel):
    score: float | None                  # None = inapplicable, NOT zero
    evidence: list[MatchEvidence]
    missing: list[MissingItem]
    warnings: list[ScoringWarning]

class MatchResult(BaseModel):
    job_id: UUID
    candidate_id: UUID
    run_id: UUID
    required_score: float | None
    experience_score: float | None
    responsibility_score: float | None
    preferred_score: float | None
    applied_weights: dict[str, float]    # sums to 1.0 over applicable components
    final_score: float                   # 0–100, rounded to 2 dp
    matched_evidence: list[MatchEvidence]
    missing_items: list[MissingItem]
    warnings: list[ScoringWarning]
    scoring_version: str
```

**Schema invariants (validated by pydantic validators + tests):**

- All component scores are `None` or in `[0, 100]`; `final_score` in `[0, 100]`.
- `applied_weights` values sum to `1.0 ± 1e-9`.
- `importance ∈ {1, 2, 3}`; `evidence_strength ∈ {0.0, 0.5, 0.8, 0.9, 1.0}` for exact tiers (related-skill values come from taxonomy config).
- Every `MatchEvidence.evidence_text` is non-empty.

---

## 6. Persistence design

### 6.1 Tables (SQLAlchemy models → Alembic migration 0001)

**`jobs`**

| Column | Type | Notes |
|---|---|---|
| id | GUID PK | |
| title | VARCHAR NULL | Extracted or entered |
| raw_description | TEXT | Original pasted text |
| minimum_relevant_years | NUMERIC NULL | Explicit statements only |
| confirmed | BOOLEAN default false | Frozen when true |
| parser_version | VARCHAR | |
| created_at | TIMESTAMPTZ | |

**`job_requirements`** — id GUID PK; job_id FK; requirement_type VARCHAR; canonical_name VARCHAR; original_text TEXT; importance SMALLINT (CHECK 1–3); confidence NUMERIC (CHECK 0–1); is_required BOOLEAN; allows_equivalent_experience BOOLEAN; equivalent_years NUMERIC NULL; degree_level VARCHAR NULL; field_of_study VARCHAR NULL.

**`job_responsibilities`** — id GUID PK; job_id FK; original_text TEXT; normalized_text TEXT; position INTEGER.

**`candidates`** — id GUID PK; display_identifier VARCHAR; created_at TIMESTAMPTZ. *(Contact info, if ever stored, goes in a separate isolated table that no scoring code imports; the MVP does not store it at all.)*

**`resumes`** — id GUID PK; candidate_id FK; original_filename VARCHAR (audit/UI only); file_path TEXT; file_hash VARCHAR UNIQUE; mime_type VARCHAR; raw_text TEXT; parsed_json JSON/JSONB (full `CandidateProfile` dump); parser_version VARCHAR; uploaded_at TIMESTAMPTZ.

**`employment_records`** — id GUID PK; candidate_id FK; normalized_title VARCHAR NULL; original_title VARCHAR NULL; company VARCHAR NULL (never scored); start_date DATE NULL; end_date DATE NULL; is_current BOOLEAN; date_confidence NUMERIC; description TEXT.

**`evidence_bullets`** — id GUID PK; candidate_id FK; employment_id FK NULL; section_type VARCHAR; original_text TEXT; normalized_text TEXT.

**`candidate_qualifications`** — id GUID PK; candidate_id FK; qualification_type VARCHAR; canonical_name VARCHAR; original_text TEXT; evidence_section VARCHAR; evidence_strength NUMERIC; confidence NUMERIC.

**`scoring_runs`** *(added beyond the blueprint — makes freezing/invalidation concrete)*

| Column | Type | Notes |
|---|---|---|
| id | GUID PK | |
| job_id | FK jobs | |
| status | VARCHAR | `active` \| `invalidated` |
| scoring_version | VARCHAR | e.g. `mvp-1.0` |
| parser_version | VARCHAR | |
| taxonomy_version | VARCHAR | from `config/taxonomy/VERSION` |
| config_snapshot | JSON | full scoring.yaml at run time |
| candidate_ids | JSON | frozen ordered batch list |
| created_at | TIMESTAMPTZ | |

**`match_results`** — id GUID PK; run_id FK scoring_runs; job_id FK; candidate_id FK; required_score / experience_score / responsibility_score / preferred_score NUMERIC NULL; applied_weights JSON; final_score NUMERIC; created_at TIMESTAMPTZ. **UNIQUE (run_id, candidate_id)**.

**`match_evidence`** — id GUID PK; match_result_id FK; requirement_id FK NULL; responsibility_id FK NULL; matched_canonical VARCHAR; evidence_text TEXT; evidence_section VARCHAR; raw_strength NUMERIC; adjusted_strength NUMERIC.

**`missing_items`** — id GUID PK; match_result_id FK; requirement_id FK; canonical_name VARCHAR; status VARCHAR; note TEXT.

**`scoring_warnings`** — id GUID PK; match_result_id FK; code VARCHAR; message TEXT; related_requirement_id GUID NULL.

### 6.2 Lifecycle rules

- Editing a job **after** it has an `active` scoring run → that run's status becomes `invalidated`; the job returns to unconfirmed; UI clearly marks stale results.
- Re-scoring always creates a **new** run (new vectorizer fit). Old runs remain readable for reproducibility.
- All per-run writes (results + evidence + missing + warnings) commit in **one transaction**; any failure rolls back the entire run so no partial results exist.
- A persisted score without its evidence rows is treated as corrupt by the UI.

---

## 7. Configuration

### 7.1 `config/scoring.yaml` (authoritative defaults)

```yaml
scoring_version: "mvp-1.0"

weights:                    # must be ≥0 and sum to exactly 1.0
  required: 0.45
  experience: 0.20
  responsibility: 0.20
  preferred: 0.15

responsibility_matching:
  minimum_similarity: 0.20        # weak-match threshold
  role_relevance_threshold: 0.30  # avg bullet similarity for role relevance
  ngram_min: 1
  ngram_max: 2
  sublinear_tf: true

evidence_strength:
  demonstrated: 1.00        # employment/project/research bullet
  summary: 0.90
  skills_section: 0.80
  related_default: 0.50     # only when taxonomy explicitly approves

job_parsing:
  auto_include_confidence: 0.80   # ≥ → include normally
  review_confidence: 0.60         # ≥ → include but highlight; < → exclude until confirmed
  min_description_chars: 100
  max_description_chars: 50000

uploads:
  maximum_resume_mb: 10
  allowed_extensions: [pdf, docx]
  min_extracted_chars: 200        # below → probable scan

labels:                     # descriptive only, never decisions
  strong: 85
  good: 70
  possible: 55
```

### 7.2 Settings loading & validation (`config/settings.py`)

- `pydantic-settings` loads `.env` (`DATABASE_URL`, `UPLOAD_DIR`, `SCORING_CONFIG_PATH`) and parses `scoring.yaml` into typed models.
- **Startup validation — the app refuses to start if:** any weight is negative; weights don't sum to 1.0 (±1e-9); thresholds outside [0,1]; label boundaries not descending; taxonomy files missing or invalid JSON; `VERSION` file missing.
- The exact config used for a run is snapshotted into `scoring_runs.config_snapshot`.

### 7.3 Taxonomy file formats

**skills.json** (~150–200 entries, data/analytics + software domain):

```json
{
  "power bi": {
    "aliases": ["powerbi", "microsoft power bi", "power-bi"],
    "category": "business intelligence",
    "related_skills": { "tableau": 0.5 }
  },
  "sql": {
    "aliases": ["structured query language", "postgresql", "mysql", "t-sql"],
    "category": "database query language",
    "related_skills": {}
  }
}
```

Rules: keys are canonical lowercase names; alias→canonical mapping is built at load and must be collision-free (startup error otherwise); `related_skills` partial credit applies **only** where listed — categories never imply interchangeability.

**degrees.json** — ladder `high_school < associate < bachelor < master < doctorate` plus alias map (`"b.s." → bachelor`, `"bsc" → bachelor`, `"m.tech" → master`, ...).

**fields.json** *(added beyond blueprint — powers the 0.75 tier)*:

```json
{
  "computer science": {
    "related": ["software engineering", "information technology"],
    "somewhat_related": ["mathematics", "statistics", "data science"]
  }
}
```

`related` → field score 1.00; `somewhat_related` → 0.75; otherwise 0.00. Symmetry is not assumed; each direction is listed explicitly.

**certifications.json** — canonical cert/license entries with aliases and explicitly approved `equivalents` / `related` (with partial values). License equivalence is **only** manual — never inferred by similarity.

**titles.json** — canonical titles with `aliases` and `related_titles` lists used for experience relevance.

**phrase_normalization.json** — small controlled map applied before TF-IDF (`"built"→"developed"`, `"executives"→"management"`, `"kpis"→"kpi"`, ...). Originals always kept for display.

**VERSION** — single string, bumped whenever any taxonomy file changes; recorded on every run.

---

## 8. File ingestion and validation

### 8.1 Per-file validation sequence (each step short-circuits with a status)

1. Extension ∈ {`.pdf`, `.docx`} → else `unsupported`.
2. Size ≤ 10 MB → else `unsupported` (with size message).
3. Magic-bytes/signature check: PDF starts `%PDF`; DOCX is a ZIP (`PK\x03\x04`) containing `word/document.xml`. Extension alone is never trusted → mismatch = `unsupported`.
4. SHA-256 of raw bytes; hash already present in this batch or DB → `duplicate` (no new candidate created).
5. Text extraction in memory (Section 8.2); library exception or password-protected → `corrupt`.
6. Extracted text < `min_extracted_chars` (200) → `probable_scan` ("OCR is not supported in the MVP").
7. Persist file to `uploads/{sha256}.{ext}` (server-generated name; original filename stored only as audit metadata; filenames sanitized).
8. Parse into `CandidateProfile` → `accepted` or `parsed_with_warnings`; unexpected parser crash → `failed` for that file only — **the batch always continues**.

### 8.2 Extraction functions (exact contracts)

```python
import fitz
def extract_pdf_text(file_bytes: bytes) -> str:
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        if doc.needs_pass:
            raise CorruptFileError("password-protected")
        return "\n".join(page.get_text("text") for page in doc)

from io import BytesIO
from docx import Document
def extract_docx_text(file_bytes: bytes) -> str:
    document = Document(BytesIO(file_bytes))
    paragraphs = [p.text for p in document.paragraphs]
    table_text = [cell.text for t in document.tables
                  for row in t.rows for cell in row.cells]
    return "\n".join(paragraphs + table_text)
```

Uploaded content is **data only** — nothing from a document is ever executed, evaluated, or interpolated into queries/paths.

---

## 9. Resume parsing

### 9.1 Section detection

Heading dictionary (case-insensitive, punctuation-tolerant, matched on heading-like lines: short, title-cased/upper-cased, often ending without a period):

| Observed headings | Canonical section |
|---|---|
| Professional Experience, Work Experience, Employment History, Experience | experience |
| Technical Skills, Skills, Core Competencies, Tools | skills |
| Projects, Academic Projects, Personal Projects | projects |
| Research, Research Experience, Publications | research |
| Education, Education and Training, Academic Background | education |
| Certifications, Licenses & Certifications, Licenses | certifications |
| Summary, Professional Summary, Profile, Objective, About Me | summary |
| Interests, Hobbies, References, Volunteering | excluded |

No headings detected → resume remains parseable (whole body treated as unsectioned experience-like text) + warning `NO_HEADINGS` with lowered confidence.

### 9.2 Evidence bullets

Built from employment descriptions, projects, and research sections — split on bullet glyphs (•, -, *, –) and sentence boundaries (spaCy). **Never** from: contact header, summary, skills lists, education, certifications, interests, references, or company-boilerplate lines. Each bullet stores original + normalized text and its parent employment record when applicable.

### 9.3 Skill extraction

- Longest-match-first dictionary matching over normalized text using the alias map (e.g., `machine learning` matches before `learning`; `power bi` before `bi`).
- Each canonical skill is recorded **once**, keeping its strongest evidence:

| Evidence location | Strength |
|---|---:|
| Employment / project / research bullet | 1.00 |
| Summary section | 0.90 |
| Skills section only | 0.80 |
| Approved related skill (taxonomy) | configured (default 0.50) |
| Not found | 0.00 |

- Repetition never adds points. Section context comes from the section detector.

### 9.4 PII stripping (three layers, applied before any scoring input is built)

1. **Regex layer:** emails, phone numbers (international-tolerant), URLs/social handles, and street-address patterns are removed from scoring text.
2. **Header layer:** all text above the first detected section heading is classified as the contact block and excluded from scoring inputs (it is where names/addresses/photo captions live).
3. **NER backstop:** spaCy PERSON entities in scoring text are masked.

Additionally: graduation years are dropped at education-extraction time; age/DOB/gender/pronoun/marital/nationality patterns are stripped; photographs are never extracted (text-only pipeline). `raw_resume_text` is stored for audit but is **never** an input to matching or scoring. Company names may appear in displayed evidence but carry zero scoring value. Acceptance test: changing only the candidate's name yields a bit-identical score.

### 9.5 Education extraction

Degree level (via degrees.json aliases), field of study (via fields.json vocabulary), completion status when explicit ("expected", "in progress" → `completed=False`), original evidence text. No graduation year.

### 9.6 Certification / license extraction

Dictionary + aliases. Held vs not-held rules:

| Wording pattern | held | Notes |
|---|---|---|
| "X certified", "X, issued 2025", "X (Active)" | Yes | |
| "X candidate", "pursuing X", "preparing for X" | No | warning `PENDING_CREDENTIAL` |
| "X coursework", "X training" | No | |

Issue years are ignored for scoring. License equivalence only via explicit taxonomy entries.

### 9.7 Employment extraction and dates

- Title line + company + date-range detection per role block; titles normalized via titles.json.
- Date formats: `Jan 2020 – Mar 2023`, `01/2020 - 03/2023`, `2020–2023`, `2019 – Present`.
- `Present`/`Current` → `is_current=True`; effective end date = scoring-run date.
- Year-only start → Jan 1 internally; year-only end → Dec 31 internally; both lower `date_confidence` (1.0 → 0.6) and add warning `YEAR_ONLY_DATE`.
- End before start → interval discarded + warning `INVALID_DATE_RANGE` (never crashes).
- Unparseable dates → role kept for qualifications/bullets, excluded from experience years, warning `MISSING_DATES` ("experience may be underestimated").

---

## 10. Job-description parsing

### 10.1 Input validation

Reject with a clear message when: empty; < 100 chars; > 50,000 chars; mostly non-text symbols; or when parsing finds zero qualifications **and** zero responsibilities ("nothing scoreable — please edit the description or add items manually on the confirmation page").

### 10.2 Section detection (job side)

| Observed headings | Canonical section |
|---|---|
| Responsibilities, What You Will Do, Duties, Key Activities, The Role | responsibilities |
| Requirements, Minimum Qualifications, Must Have, What You Need | required |
| Preferred Qualifications, Nice to Have, Desired, Bonus Points | preferred |
| About Us, Company, Who We Are | excluded |
| Benefits, Compensation, Perks, EEO statements | excluded |

Same algorithm as resumes: detect heading lines, assign following lines until the next heading. If no headings exist, classify sentence-by-sentence using cue phrases.

### 10.3 Required/preferred classification

Cues (case-insensitive):

- **Required:** required, must have, must possess, mandatory, minimum qualification, essential, candidates must, minimum of.
- **Preferred:** preferred, desired, ideally, a plus, nice to have, bonus, familiarity with, exposure to.

Priority: **(1)** explicit sentence wording beats **(2)** section heading beats **(3)** ambiguous (flagged for review). Example: "Python is preferred" inside a Requirements section → preferred.

### 10.4 Requirement extraction

Within classified sentences, extract items by type: skills (taxonomy longest-match), education (degree pattern + field), certifications/licenses (taxonomy), and detect "or equivalent experience" → `allows_equivalent_experience=True` (+ `equivalent_years` only if a number is stated; otherwise flag for recruiter review — never invent it).

**Importance assignment:** 3 = explicit "must/mandatory/required" wording on the item; 2 = standard item in a required list; 1 = weak wording or recruiter-added supporting item. Cap 3; repetition never raises it. Duplicate canonical items merge, keeping highest importance.

### 10.5 Extraction confidence (deterministic, additive; labeled "extraction confidence", never a probability)

Start 0.30, add: +0.25 known taxonomy match; +0.20 explicit required/preferred cue; +0.15 recognized section heading; +0.10 clean numeric experience pattern or exact degree/cert pattern. Clamp to [0,1].

| Confidence | Behavior |
|---:|---|
| ≥ 0.80 | Include, display normally |
| 0.60–0.79 | Include, highlighted for review |
| < 0.60 | Excluded from scoring until recruiter explicitly confirms it |

Confidence controls workflow only — it is **never** multiplied into candidate scores.

### 10.6 Experience-minimum extraction

Patterns: `3+ years`, `at least three years`, `minimum of 2 years`, `two to four years`, `5 years of relevant experience` (written numbers zero–twenty converted). Rules: `3+` → 3; range `2–4` → 2; store only when explicitly tied to experience wording; **never** infer from "senior"; multiple minimums → the general minimum drives the experience component, skill-specific ones remain as requirement metadata. No explicit minimum → `minimum_relevant_years=None` → component inapplicable.

### 10.7 Responsibilities

Bullets/sentences from the responsibilities section: keep original, produce normalized text (Section 12.2), preserve order via `position`. Benefits/company text can never become responsibilities or qualifications (test-enforced).

### 10.8 Confirmation page contract

Displays required, preferred, experience minimum, responsibilities, and low-confidence/excluded items — each with original source text and confidence. Recruiter can add, edit, delete, and move items between required/preferred. **Confirm and Continue** sets `confirmed=True` and freezes the profile. Any later edit → new unconfirmed revision + invalidation of existing runs (Section 6.2). Unconfirmed jobs cannot be scored (hard assertion in the engine).

---

## 11. Scoring model — qualifications (required & preferred)

Exactly four components exist in the MVP. Education, certifications, and licenses are **not** separate components — they are qualification items inside required/preferred.

| Component | Default weight |
|---|---:|
| Required qualifications | 0.45 |
| Relevant experience | 0.20 |
| Responsibility similarity | 0.20 |
| Preferred qualifications | 0.15 |

### 11.1 Shared formula (required and preferred use identical mechanics)

For items `i = 1…n` in the category:

```text
score = 100 * Σ(importance_i × match_i) / Σ(importance_i)      match_i ∈ [0, 1]
```

Empty category → `None` (inapplicable), never 0, never free points.

### 11.2 Skill match values

| Evidence | match value |
|---|---:|
| Exact/alias skill demonstrated in experience/project/research bullet | 1.00 |
| Exact/alias skill in summary | 0.90 |
| Exact/alias skill in skills section only | 0.80 |
| Taxonomy-approved related skill | configured (default 0.50) |
| Not found | 0.00 |

Strongest single evidence wins; mentions never sum.

### 11.3 Education match

```text
degree_level_score: meets/exceeds = 1.00 | one level below = 0.50 | lower/absent = 0.00
field_score:        listed or "related" = 1.00 | "somewhat_related" = 0.75 | else 0.00
education_match = degree_level_score × field_score
```

Level-only requirement (no field stated) → use `degree_level_score` alone.
"Degree **or equivalent experience**":

```text
education_match = max(degree_match, min(relevant_years / stated_equivalent_years, 1.0))
```

If equivalent years are not stated in the description, do not invent them — the requirement is flagged for recruiter review on the confirmation page.

### 11.4 Certification / license match

| Evidence | match value |
|---|---:|
| Exact credential or taxonomy-approved equivalent, held | 1.00 |
| Taxonomy-approved related (non-equivalent) credential | configured partial |
| Candidate/pending/preparing/coursework | 0.00 + warning |
| Not identified | 0.00 + verification warning when legally required |

A missing required license lowers the score and shows a recruiter-verification warning — it never auto-rejects.

### 11.5 Worked example (canonical test fixture)

```text
Required:  SQL imp 3 × 1.00 | Excel imp 2 × 0.80 | Related bachelor imp 2 × 1.00
required_score = 100 × (3 + 1.6 + 2) / 7 = 94.29  (2 dp)

Preferred: Python imp 2 × 1.00 | Power BI imp 2 × 0.80 | Healthcare imp 1 × 0.00
preferred_score = 100 × (2 + 1.6 + 0) / 5 = 72.00
```

---

## 12. Scoring model — responsibility similarity

### 12.1 Inputs

Job side: confirmed responsibility texts. Candidate side: evidence bullets from employment/projects/research only. Skills lists, summary, education, contact, and interests are excluded.

### 12.2 Normalization for matching copies (originals always preserved for display)

1. lowercase → 2. collapse whitespace/punctuation → 3. apply `phrase_normalization.json` → 4. `TfidfVectorizer` removes English stop words → 5. unigrams + bigrams.

### 12.3 Vectorizer (exact configuration)

```python
TfidfVectorizer(lowercase=True, stop_words="english",
                ngram_range=(1, 2), sublinear_tf=True, norm="l2")
```

**One vectorizer per scoring run**, fit on all job responsibilities + all bullets of all batch candidates, reused for every candidate. Per-candidate fitting is forbidden (IDF would differ). Batch changes → new run.

### 12.4 Matrix and selection

```python
matrix = cosine_similarity(job_vectors, resume_vectors)   # shape m × n
best_i = matrix[i].max()                                  # per responsibility
adjusted_best_i = best_i if best_i >= 0.20 else 0.0       # weak-match threshold
responsibility_score = 100 * mean(adjusted_best_i)        # equal responsibility weights
```

Both raw and adjusted values are persisted and displayed. One bullet may serve several responsibilities; the UI makes the repetition visible.

### 12.5 Contract and edge rules

```python
def calculate_responsibility_score(job_responsibilities, candidate_bullets,
                                   fitted_vectorizer, minimum_similarity=0.20
                                   ) -> ComponentResult: ...
```

- No job responsibilities → `score=None` (inapplicable).
- Responsibilities exist, candidate has zero bullets → `score=0` + warning `NO_EVIDENCE_BULLETS`.
- Every responsibility appears in the output with its best bullet (or explicit no-match).

Worked fixture: bests `0.76, 0.65, 0.58` → `100 × 1.99/3 = 66.33`.

Known limitation (documented in README): TF-IDF misses synonym-only matches; the phrase-normalization map is the MVP mitigation; embeddings are explicitly deferred.

---

## 13. Scoring model — experience, weights, final score

### 13.1 Experience applicability

Computed **only** when the job states an explicit minimum. No stated minimum → `None` + weight redistribution. Seniority words never imply a minimum.

### 13.2 Role relevance (a role counts if either passes)

1. Its normalized title appears in the target title's `related_titles` list (titles.json); **or**
2. Mean cosine similarity of its bullets vs. job responsibilities ≥ `role_relevance_threshold` (0.30), using the run's fitted vectorizer.

Each counted interval stores its relevance reason (`title_match` / `similarity`). If the job has an experience minimum but **zero responsibilities**, only path 1 exists → warning `TITLE_ONLY_RELEVANCE`.

### 13.3 Duration calculation

1. Take relevant intervals with valid dates. 2. Drop invalid/unknown ones (warned, per 9.7). 3. **Merge overlaps** (sort by start; coalesce overlapping/touching intervals) so parallel jobs never double-count calendar time. 4. Sum merged days. 5. `years = days / 365.25`. Undated projects contribute skills/bullets but never years.

### 13.4 Formula

```text
experience_score = 100 × min(relevant_years / required_years, 1.0)
```

Fixture: 2.5 of 3.0 → 83.33. 5 of 3 → 100 (never above 100). Missing dates → computed from valid intervals + warning "may be underestimated" (never silently zero).

### 13.5 Dynamic weight normalization

```python
def normalize_weights(scores: dict[str, float | None],
                      default_weights: dict[str, float]) -> dict[str, float]:
    applicable = {k: w for k, w in default_weights.items() if scores[k] is not None}
    total = sum(applicable.values())
    if total == 0:
        raise UnscorableJobError("No applicable scoring components")
    return {k: w / total for k, w in applicable.items()}
```

`None` = inapplicable and redistributes; `0` = applicable and keeps its weight. Fixture: preferred absent → 0.45/0.85, 0.20/0.85, 0.20/0.85 = 0.5294 / 0.2353 / 0.2353.

### 13.6 Final score, ties, labels

```text
final = Σ (component_score × normalized_weight)      # rounded to 2 dp
Fixture: 94.29×0.45 + 83.33×0.20 + 66.33×0.20 + 72.00×0.15 = 83.17
```

Tie-break order: final ↓, required ↓, responsibility ↓, display_identifier ↑. No hidden criteria.

| Score | Label (descriptive only) |
|---:|---|
| 85–100 | Strong match |
| 70–84.99 | Good match |
| 55–69.99 | Possible match |
| < 55 | Limited match based on resume evidence |

---

## 14. Scoring engine orchestration

### 14.1 Per-candidate contract

```python
def score_candidate(job: JobProfile, candidate: CandidateProfile,
                    context: ScoringContext) -> MatchResult:
    assert job.confirmed
    responsibility = calculate_responsibility_score(...)
    experience     = calculate_experience_match(...)     # may reuse vectorizer
    required       = match_qualifications(job.required_qualifications, ...)
    preferred      = match_qualifications(job.preferred_qualifications, ...)
    weights        = normalize_weights({...}, context.default_weights)
    final          = round(sum(score × weight), 2)
    return MatchResult(..., scoring_version=context.scoring_version)
```

`ScoringContext` carries: fitted vectorizer, taxonomy, thresholds, default weights, run date (for `Present`), and all version strings. It is built once per run and shared by every candidate.

### 14.2 Batch algorithm (service layer)

1. Assert job confirmed; create `scoring_runs` row (status `active`) with config snapshot + versions + frozen candidate list.
2. Fit vectorizer (Section 12.3).
3. Score each candidate; collect results.
4. Persist run, results, evidence, missing items, warnings in **one transaction**; on any error, roll back everything and surface a safe message.
5. Rankings always read from persisted rows, never from in-memory leftovers.

### 14.3 Deterministic identifiers

Candidates in a run are sorted by file SHA-256 (ascending hex) and numbered `Candidate 001…N`. Identical file sets therefore always produce identical identifiers, orderings, and exports — satisfying the reproducibility requirement without exposing names.

---

## 15. User interface (Streamlit)

### 15.1 State & gating

`st.session_state` keys: `job_id`, `job_confirmed`, `batch_candidate_ids`, `run_id`. Every page begins with a gate: Confirm requires a parsed job; Upload requires a confirmed job; Rankings/Details require a completed `active` run — otherwise the page shows a friendly redirect message. This enforces the confirm → freeze → score workflow at the UI level while the service layer enforces it with assertions (defense in depth).

### 15.2 Pages

**1 — Create Job:** required description textarea, optional title, character counter, **Analyze Description** button; validation errors from Section 10.1 shown inline.

**2 — Confirm Job Profile:** editable tables for required, preferred, responsibilities; experience-minimum field; each extracted row shows original evidence text + confidence badge (normal / highlighted / excluded-pending-confirmation per 10.5); actions add / edit / delete / move required↔preferred; **Confirm and Continue** freezes the profile. Editing a previously confirmed job triggers the invalidation flow with an explicit warning dialog.

**3 — Upload Resumes:** multi-file uploader; per-file status table (accepted / duplicate / unsupported / corrupt / probable scan / parsed with warnings / failed) with reason text; only successfully parsed candidates join the batch; **Score Candidates** button (disabled until ≥1 parsed candidate).

**4 — Rankings:** table `Rank | Candidate | Final | Label | Required | Experience | Responsibilities | Preferred | Warnings`; `None` components render as "N/A (not applicable)" — never as 0; filters: score range, has-warnings; CSV download button; the mandatory oversight notice (Section 17.3) is permanently visible on this page.

**5 — Candidate Details:** final score + applied weights (shown so redistribution is visible); component breakdown; matched required and preferred qualifications each with evidence text, section, and strength; missing/unclear items with the "not proof of absence" phrasing; relevant employment intervals with dates, merge results, and relevance reason; every job responsibility with its best bullet plus raw and adjusted similarity; all parsing and scoring warnings.

### 15.3 Export (CSV, exact columns in order)

```text
rank, candidate_identifier, final_score, required_score, experience_score,
responsibility_score, preferred_score, matched_required_count,
missing_required_count, warning_count, scoring_version
```

Inapplicable components export as empty cells. No resume text, no names, no contact data in the export. Export values must equal persisted values exactly (integration-tested).

---

## 16. Error and edge-case handling (complete required-behavior table)

| Condition | Required behavior |
|---|---|
| Empty job description | Block parsing with message |
| Description too short/long/garbled | Block with specific reason |
| Nothing scoreable extracted | Require recruiter edits; scoring disabled |
| Requirement confidence < 0.60 | Exclude from scoring until recruiter confirms |
| Requirement confidence 0.60–0.79 | Include + highlight for review |
| No preferred qualifications | `None` + redistribute weight |
| No explicit experience minimum | `None` + redistribute weight |
| No responsibilities | `None` + redistribute weight; experience relevance falls back to titles (+warning) |
| No applicable components at all | `UnscorableJobError`; recruiter told the job can't be scored as extracted |
| Candidate has zero evidence bullets | Responsibility score 0 + warning |
| Missing/partial employment dates | Score valid intervals + "may be underestimated" warning |
| Overlapping employment | Merge intervals; never double-count |
| End date before start date | Discard interval + warning; never crash |
| Scanned/image resume | Reject with "OCR required — not supported in MVP" |
| Password-protected/corrupt file | Reject that file; batch continues |
| Duplicate file (hash) | No duplicate candidate in the batch |
| Required license not found | Missing + recruiter-verification warning; **no auto-rejection** |
| Parser crash on one resume | That file `failed`; all others proceed |
| DB write failure during run | Full-run rollback; safe error; no partial results |
| Job edited after scoring | Existing run(s) `invalidated`; results marked stale |
| Candidate added after scoring | New run with new vectorizer required |
| `PowerBI` vs `power bi` etc. | Alias normalization matches them identically |
| "PMP candidate" | Not held; 0.00 + pending warning |

---

## 17. Security, privacy, and responsible use

### 17.1 Scoring exclusions (stripped or isolated before scoring — Section 9.4 mechanism)

Name; email/phone; street address; photograph; age/birth date; graduation year; gender/pronouns; race/ethnicity/national origin/religion; disability/health; marital/family status. Company names may appear in displayed evidence but never add score.

### 17.2 Data handling rules

Only synthetic resumes in the repository; real resumes never sent to external services; secrets only in `.env` (git-ignored, with `.env.example` template); `uploads/` git-ignored and access-restricted; logging never includes resume text or PII (log codes + hashes only); filenames sanitized, storage names server-generated; document content is never executed; deletion = removing candidate rows cascades to qualifications/bullets/results and the stored file (documented retention behavior).

### 17.3 Mandatory human-oversight notice (verbatim, on every ranking view)

> This score reflects evidence identified in the submitted resume and is intended to support recruiter review. It is not an employment decision.

---

## 18. Testing strategy

### 18.1 Unit tests (written **before** the corresponding implementation)

Job parsing: "must have SQL" → required SQL; "Python is a plus" → preferred; "Python is preferred" inside Requirements → preferred (wording beats heading); "3+ years" → 3.0; "two to four years" → 2.0; benefits text yields no qualifications; "senior" alone yields no minimum.

Resume parsing: `PowerBI` → `power bi`; skill in experience bullet → 1.00; skills-section-only → 0.80; summary → 0.90; "PMP candidate" → not held + warning; year-only dates → Jan-1/Dec-31 + lowered confidence; graduation year absent from records; email/phone/name absent from scoring text.

Qualification scoring: fixture 94.29 and 72.00 reproduce exactly; repeated skill counts once; empty category → `None`; education 11.3 math (level×field, one-level-below=0.50, somewhat-related=0.75); degree-or-equivalent uses max(); missing stated equivalent years → review flag, no invention.

Experience: 2.5/3 → 83.33; 5/3 → 100.00; overlap `[2019-01→2021-06] + [2020-01→2022-01]` merges to 3.0 years; end-before-start discarded + warning; no minimum → `None`.

Responsibilities: matrix shape m×n; best-per-responsibility selection; 0.19 → 0.0, 0.20 → kept; zero bullets → 0 + warning; zero responsibilities → `None`; fixture 66.33.

Weights & final: all four present → defaults unchanged; preferred absent → 0.5294/0.2353/0.2353; weights always sum to 1.0; all-`None` → `UnscorableJobError`; final fixture 83.17; tie-break order.

Config & taxonomy: startup rejects bad weights; alias collision detected; longest-match-first verified.

### 18.2 Integration tests

Full path paste → parse → confirm → upload → score → persist → export with in-memory SQLite; one corrupt file doesn't block the batch; single shared vectorizer per run (asserted by identity); injected DB failure leaves zero partial rows; export equals persisted values; job edit invalidates run.

### 18.3 Acceptance scenarios (synthetic data, expected outcomes documented in `expected_rankings.md`)

1. Strong candidate (all required, enough years, matching bullets) ranks first with "Strong match".
2. Keyword-stuffer (skills list only, no evidence bullets) scores clearly below demonstrated-evidence candidates.
3. Experienced candidate missing one preferred skill → small, visible preferred deduction only.
4. "Degree or equivalent experience" satisfied through years.
5. Missing required license → warning, still ranked, not rejected.
6. Job without preferred quals and without experience minimum → correct redistribution, no free points.
7. Year-only dates → scored with underestimation warning.
8. Same resume, name changed → identical score to the digit.

### 18.4 Evaluation metrics (when recruiter judgments exist)

Precision@5, Recall@10, NDCG, recruiter agreement rate, screening-time delta, parsing correction rate, % of score elements with visible evidence. Documented caveat: never tune thresholds/weights on the same tiny sample used to report results.

---

## 19. Synthetic data plan (Stage 0 deliverable)

`sample_data/generate.py` deterministically (fixed seed) produces:

- **6 job descriptions** (data analyst ×2, data engineer, BI analyst, data scientist, software engineer) with varied heading styles, one with no preferred section, one with no experience minimum.
- **25+ resumes** as real `.pdf` (PyMuPDF) and `.docx` (python-docx) files covering: strong match, good-but-gaps, keyword-stuffer, career-changer, missing dates, year-only dates, no headings, table-based DOCX, "degree or equivalent" satisfier, PMP-candidate case, plus deliberately **corrupt** file, **password-protected** PDF, **near-empty** (probable-scan) PDF, an exact **duplicate**, and a `.txt` renamed to `.pdf` (signature-check case).
- **`expected_rankings.md`**: hand-reasoned expected ordering + approximate scores for 3 jobs — the acceptance-test ground truth.

All names/contacts are fabricated. No real personal data anywhere in the repo.

---

## 20. Delivery plan (three checkpoints)

**Checkpoint A — Foundation & ingestion (Stages 0–2).** Repo structure, pinned env, settings + scoring.yaml validation, all taxonomies v1, all pydantic schemas, SQLAlchemy models + Alembic 0001 (SQLite-verified, Postgres-compatible), synthetic data generator + files, ingestion/validation/extraction, hand-calculated scoring tests written (red). *Exit:* app boots; migration from empty DB succeeds; every synthetic file gets its correct status; bad files never block a batch.

**Checkpoint B — Parsers & scoring brain (Stages 3–8).** Job parser + confidence + confirmation service; resume parser + PII stripping + evidence model; qualification/education/certification matchers; responsibility scorer with single batch vectorizer; experience scorer with interval merging; dynamic weights + final score; scoring-run persistence with transactional writes. *Exit:* every fixture number (94.29, 72.00, 83.33, 66.33, 83.17, 0.5294/0.2353/0.2353) reproduced by tests; all Section 18.1–18.2 tests green; re-runs bit-identical.

**Checkpoint C — UI, export, validation (Stages 9–10).** All five Streamlit pages with gating, evidence display, warnings, oversight notice; CSV export; acceptance scenarios 1–8 automated; README (setup, run, test, architecture overview, Postgres switch guide, known limitations); Ruff/Black clean. *Exit:* full recruiter flow demoable end-to-end on synthetic data in under five minutes; Definition of Done (Section 21) fully satisfied.

---

## 21. Definition of done

The MVP is complete when it can: accept and confirm one job description; extract required/preferred qualifications, experience minimum, and responsibilities with visible source text; accept ≥20 text-based PDF/DOCX resumes in one batch; survive individual file failures; score with exactly the four-component model of Sections 11–13; use one TF-IDF vectorizer per frozen run; show evidence for every qualification and responsibility match; distinguish missing vs unclear vs inapplicable; normalize weights dynamically; persist versioned runs (SQLite verified, PostgreSQL-ready with documented switch); export the exact CSV of Section 15.3 matching persisted values; pass all critical tests including the eight acceptance scenarios; exclude all protected data from scoring (name-swap test proves it); and reproduce identical results for identical inputs and versions.

---

## 22. Known limitations (documented honestly in README)

TF-IDF misses synonym-only semantic matches (mitigated by phrase normalization; embeddings deferred). Taxonomy coverage is domain-focused (data/analytics/software); other domains need taxonomy extension, not code changes. Extraction confidence is a rule-derived score, not a probability. Threshold values (0.20, 0.30) are starting points pending recruiter validation. English-language resumes only. Scanned resumes unsupported (no OCR).

---

## 23. Future enhancements (explicitly out of scope until the baseline is validated)

OCR; embedding/fixed-corpus semantic similarity (+ pgvector); O*NET enrichment; ATS integration; candidate→job matching; recruiter-feedback learning-to-rank; authentication/roles/audit logs; object storage; fairness monitoring on controlled datasets.

---

*End of specification. Implementation proceeds strictly against this document; any deviation discovered to be necessary will be raised, agreed, and recorded as a spec amendment before coding around it.*
