# Expected rankings — synthetic data ground truth

Hand-reasoned acceptance-test ground truth for `sample_data/`, produced per
SPECIFICATION.md Section 19. Covers the ingestion status of every resume
file, plus a full ranked, score-explained walkthrough for three jobs.

## How to read this document

- Scores are computed by hand against the exact formulas in Sections 11–13
  of SPECIFICATION.md, using the same weights as `config/scoring.yaml`
  defaults (required 0.45, experience 0.20, responsibility 0.20, preferred
  0.15).
- **Required/preferred `importance` values are this document's own
  assumption**, assigned per the Section 10.4 rule (3 = explicit
  must/mandatory wording on the item, 2 = standard required-list item, 1 =
  weak/supporting wording). The real job parser may assign different
  importance to a given sentence; if so, exact scores will shift even
  though the *ordering* and *reasoning* below should still hold.
- **Responsibility-similarity scores are estimates**, not computed from a
  real fitted `TfidfVectorizer`. They're graded qualitatively (how many of
  the job's responsibility bullets a candidate's evidence bullets plausibly
  cover, and how closely) and expressed on the 0–100 scale the real
  cosine-similarity pipeline would produce. Treat them as "this candidate
  should land in this band," not as exact fixtures — the exact-fixture
  numbers (94.29, 72.00, 83.33, 66.33, 83.17, etc.) live in Section 18.1
  and are reproduced by unit tests against small, hand-built inputs, not
  against this sample data.
- Per Section 18.4: **do not tune scoring thresholds or weights against
  this sample.** It exists to sanity-check ranking behavior and edge-case
  handling, not to calibrate the model.
- All resume dates assume a scoring-run date in mid-2026 (`Present` =
  ~2026-08), since several candidates use open-ended "Present" employment.

---

## 1. Ingestion status — all 26 resume files

Expected per-file status from the Section 8.1 validation sequence. None of
these depend on job content — they're pure ingestion/validation outcomes.

| File | Expected status | Reason |
|---|---|---|
| `job1_strong_match_analyst.pdf` | accepted | Valid PDF, well-formed sections |
| `job1_good_gaps_analyst.docx` | accepted | Valid DOCX |
| `job1_keyword_stuffer_analyst.pdf` | accepted | Valid PDF |
| `job1_career_changer_analyst.docx` | accepted | Valid DOCX |
| `job1_missing_preferred_skill_analyst.pdf` | accepted | Valid PDF |
| `job1_strong_match_analyst_duplicate.pdf` | **duplicate** | Byte-identical to `job1_strong_match_analyst.pdf` (same SHA-256); no second candidate created |
| `job2_strong_match_analyst2.pdf` | accepted | Valid PDF |
| `job2_good_gaps_analyst2.docx` | accepted | Valid DOCX |
| `job3_strong_match_engineer.pdf` | accepted | Valid PDF |
| `job3_good_gaps_engineer_table.docx` | accepted, `parsed_with_warnings` possible | Valid DOCX; skills section is a table, not paragraphs — exercises the table-cell extraction path in Section 8.2 |
| `job3_no_headings_engineer.pdf` | accepted, `parsed_with_warnings` | Valid PDF, but zero section headings → `NO_HEADINGS` warning, whole body treated as unsectioned experience-like text |
| `job3_missing_dates_engineer.docx` | accepted, `parsed_with_warnings` | Valid DOCX; employment entry has no dates → `MISSING_DATES` warning |
| `job3_year_only_dates_engineer.pdf` | accepted, `parsed_with_warnings` | Valid PDF; dates are `2019 - 2022` (year-only) → `YEAR_ONLY_DATE` warning, date_confidence lowered 1.0 → 0.6 |
| `job4_strong_match_bi.docx` | accepted | Valid DOCX |
| `job4_good_gaps_bi.pdf` | accepted | Valid PDF |
| `job5_strong_match_scientist.docx` | accepted | Valid DOCX |
| `job5_degree_or_equivalent_scientist.pdf` | accepted | Valid PDF; no degree line, resolves via equivalent-experience clause at scoring time |
| `job5_good_gaps_scientist.pdf` | accepted | Valid PDF |
| `job5_weak_scientist.docx` | accepted | Valid DOCX |
| `job6_strong_match_swe.docx` | accepted | Valid DOCX; PMP shown as held |
| `job6_pmp_candidate_engineer.pdf` | accepted, `parsed_with_warnings` | Valid PDF; "PMP candidate, exam scheduled..." → not held, `PENDING_CREDENTIAL` warning |
| `edge_corrupt_file.pdf` | **corrupt** | `.pdf` extension and starts with `%PDF-1.4`, but the body is not a real PDF structure — `fitz.open()` raises on open |
| `edge_password_protected.pdf` | **corrupt** | Valid, well-formed PDF but AES-256 encrypted — `doc.needs_pass == True` → `CorruptFileError("password-protected")` |
| `edge_probable_scan.pdf` | **probable_scan** | Valid PDF; extracts to 7 characters, far under the 200-char `min_extracted_chars` threshold |
| `edge_renamed_txt_as_pdf.pdf` | **unsupported** | Plain text content saved with a `.pdf` extension; fails the magic-bytes signature check (doesn't start with `%PDF`) |
| `edge_unsupported_filetype.doc` | **unsupported** | `.doc` is not in the allowed extension set (`{pdf, docx}`) |

Verified directly against the extraction contracts while generating this
data: the duplicate's SHA-256 matches exactly; the corrupt file raises
`FileDataError` on `fitz.open()`; the password-protected file reports
`needs_pass == True`; the probable-scan file extracts to 7 characters; the
renamed `.txt` starts with `Jordan C` instead of `%PDF`; the table-based
DOCX exposes its skills via `table.rows[*].cells[*].text`, not paragraph
text.

**Batch behavior check:** uploading all 26 files in one batch should yield
20 usable candidates (the 20 non-edge-case, non-duplicate resumes) plus 6
files with explicit non-`accepted`/`parsed_with_warnings` statuses that
never block the rest of the batch (Section 16: "one bad file never blocks
the rest").

---

## 2. Job 1 — Data Analyst (`job_01_data_analyst_standard.txt`)

**Parsed profile (assumed importance):**

| Type | Item | Importance | Required? |
|---|---|---:|---|
| skill | SQL | 3 | required |
| skill | Excel | 3 | required |
| education | Bachelor's, field ∈ {Data Analytics, Statistics, Economics, related} | 2 | required |
| skill | Power BI | 2 | preferred |
| skill | Python | 1 | preferred |
| skill | Tableau | 1 | preferred |

Minimum relevant years: **2.0** (explicit: "at least 2 years"). 5
responsibility bullets (dashboards, SQL queries, data cleaning,
stakeholder presentations, cross-team partnership).

**Ranked candidates:**

| Rank | Candidate (file) | Required | Experience | Responsibility | Preferred | Final | Label |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Jordan Ellis — `job1_strong_match_analyst.pdf` | 100.00 | 100.00 | ~95 | 75.00 | **~95.3** | Strong match |
| 2 | Dakota Reyes — `job1_missing_preferred_skill_analyst.pdf` | 92.50 | 100.00 | ~75 | 75.00 | **~87.9** | Strong match |
| 3 | Morgan Patel — `job1_good_gaps_analyst.docx` | 100.00 | 100.00 | ~40 | 50.00 | **~80.5** | Good match |
| 4 | Casey Nguyen — `job1_keyword_stuffer_analyst.pdf` | 60.00 | 0.00 | ~5 | 80.00 | **~40.0** | Limited match |
| 5 | Riley Thompson — `job1_career_changer_analyst.docx` | 60.00 | 0.00 | ~3 | 0.00 | **~27.6** | Limited match |

**Reasoning:**

- **Jordan Ellis** (acceptance scenario 1 — strong candidate): SQL and Excel
  both demonstrated in bullets (1.00 each), exact-field bachelor's degree
  (1.00), 2 roles totaling well over the 2-year minimum, bullets that
  closely mirror the job's own responsibility list, and 2 of 3 preferred
  skills demonstrated (missing only Tableau). Everything required is fully
  met and demonstrated — this is the top-ranked, "Strong match" profile.
- **Dakota Reyes** (acceptance scenario 3 — missing one preferred skill):
  Required and experience are both excellent (Excel only appears in the
  skills section, not a bullet, pulling required down slightly to 92.50);
  the only real gap is a missing preferred skill (Tableau) plus slightly
  thinner responsibility coverage. The deduction from Jordan Ellis's score
  is real but small (~7 points) and comes entirely from the preferred
  component and responsibility coverage — never from a collapse in
  required or experience. This is exactly the "small, visible preferred
  deduction only" behavior Section 18.3 scenario 3 calls for.
- **Morgan Patel**: required qualifications are all fully met (SQL, Excel,
  and Power BI are all demonstrated in bullets; the business-analytics
  degree is treated as a related field), so this candidate is *not*
  distinguished from the top two on the required component. What actually
  separates "good" from "strong" here is coverage: only 3 of 5 job
  responsibilities are evidenced, and 2 of 3 preferred skills (Python,
  Tableau) are entirely absent. This is a deliberate illustration that a
  fully-qualified-on-paper candidate can still land as only a "Good match"
  once responsibility and preferred-skill coverage are weighed in.
- **Casey Nguyen** (acceptance scenario 2 — keyword-stuffer): lists every
  required and preferred skill in a skills-only section (each capped at
  0.80, never 1.00, since nothing is demonstrated), has an unrelated
  degree field (Communications → field_score 0.0), and an unrelated
  admin-coordinator work history with zero bullets resembling any job
  responsibility. Required score (60.00) and preferred score (80.00) look
  deceptively decent from the skills list alone, but experience (0.00) and
  responsibility (~5) collapse the final score to ~40 — clearly below
  every demonstrated-evidence candidate, exactly as scenario 2 requires.
- **Riley Thompson** (career-changer): same required score as the
  keyword-stuffer (unrelated degree field, skills-section-only evidence)
  but *zero* preferred-skill coverage (no Power BI/Python/Tableau
  anywhere) and zero relevant experience, landing just below the
  keyword-stuffer. Worth flagging honestly: this ordering (keyword-stuffer
  narrowly outscoring an honest career-changer) is a real, minor side
  effect of skills-list credit rather than a bug — it does not change
  either candidate's "Limited match" label, and both score roughly a third
  of the top candidate.

---

## 3. Job 3 — Data Engineer (`job_03_data_engineer.txt`)

**Parsed profile (assumed importance):**

| Type | Item | Importance | Required? |
|---|---|---:|---|
| skill | SQL | 3 | required |
| skill | Python | 3 | required |
| skill | ETL / Data Pipelines | 3 | required |
| education | Bachelor's, field ∈ {Computer Science, related} | 2 | required |
| skill | Airflow | 1 | preferred |
| skill | AWS | 2 | preferred |
| skill | Docker | 1 | preferred |

Minimum relevant years: **3.0**. 5 responsibility bullets (build/maintain
ETL pipelines, monitor/resolve failures, optimize SQL, collaborate on data
models, document lineage).

**Ranked candidates:**

| Rank | Candidate (file) | Required | Experience | Responsibility | Preferred | Final | Label |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Taylor Brooks — `job3_strong_match_engineer.pdf` | 94.55 | 100.00 | ~88 | 100.00 | **~95.2** | Strong match |
| 2 | Charlie Fenwick — `job3_no_headings_engineer.pdf` | 100.00 | ~100 | ~80 | 75.00 | **~92.3** (see caveat) | Strong match, flagged |
| 3 | Peyton Marsh — `job3_year_only_dates_engineer.pdf` | 100.00 | 100.00 | ~60 | 0.00 | **~77.0** | Good match, YEAR_ONLY_DATE warning |
| 4 | Jamie Ortiz — `job3_good_gaps_engineer_table.docx` | 95.45 | 100.00 | ~55 | 0.00 | **~74.0** | Good match |
| 5 | Skyler Vance — `job3_missing_dates_engineer.docx` | 100.00 | 0.00 | ~65 | 0.00 | **~58.0** | Possible match, MISSING_DATES warning |

**Reasoning:**

- **Taylor Brooks**: every required item demonstrated in bullets except
  Python (skills-section-only, since no bullet literally says "Python"),
  all three preferred items (Airflow, AWS, Docker) demonstrated, strong
  responsibility overlap. Clear top rank.
- **Charlie Fenwick** (`NO_HEADINGS` case): with zero section headings, the
  whole resume body is treated as one unsectioned, experience-like block
  per Section 9.1, so skills mentioned inline still count as
  fully-demonstrated (1.00) and sentence-segmented text still feeds the
  responsibility matcher. On paper this produces a very high score — but
  it should always surface with a `NO_HEADINGS` warning and reduced
  parsing confidence, and the employment dates ("March 2022 to present")
  are embedded in prose rather than a clean title/company/date block, so
  real extraction may be less clean than this estimate assumes. **This
  candidate is intentionally ranked near the top with a visible warning**
  to test that the UI surfaces the warning prominently rather than letting
  a high score imply high confidence.
- **Peyton Marsh** (acceptance scenario 7 — year-only dates): `2019 -
  2022` resolves internally to Jan 1, 2019 – Dec 31, 2022 (~4.0 years),
  clearing the 3-year minimum, but with `date_confidence` lowered from 1.0
  to 0.6 and a `YEAR_ONLY_DATE` warning attached. No preferred skills
  mentioned at all, so responsibility and preferred coverage keep this out
  of "Strong match" territory despite full required/experience credit.
- **Jamie Ortiz** (table-based DOCX): required score is slightly below
  100 because the degree field (Information Systems) is treated as
  "related" rather than an exact match (0.75 field tier), and — more
  importantly — this candidate has zero preferred-skill coverage (no
  Airflow/AWS/Docker) and only partial responsibility coverage (pipeline
  building and SQL, but no monitoring/alerting or lineage documentation).
  The skills table (SQL, Python, Data Pipelines) must be extracted via
  DOCX table-cell text, not paragraph text — this is the primary purpose
  of this fixture.
- **Skyler Vance** (missing dates): required qualifications are all fully
  met, but the single employment entry has no dates at all, so it's
  excluded entirely from the experience-years calculation (Section 9.7 /
  13.3) — 0 relevant years counted against a 3-year minimum, dropping
  experience to 0.00 despite `MISSING_DATES` warning text explicitly
  saying "experience may be underestimated." This is the clearest
  illustration in the sample set of why that warning exists: the
  candidate is almost certainly more experienced than their score
  suggests, and a recruiter should not read 58.00 at face value here.

---

## 4. Job 5 — Data Scientist (`job_05_data_scientist.txt`)

**Parsed profile (assumed importance):**

| Type | Item | Importance | Required? |
|---|---|---:|---|
| skill | Python | 3 | required |
| skill | SQL | 3 | required |
| skill | Machine Learning | 3 | required |
| education | Master's, field ∈ {Statistics, CS, Data Science}, **or 4.0 years equivalent experience** | 2 | required |
| skill | Deep Learning | 1 | preferred |
| skill | Power BI | 2 | preferred |
| skill | Tableau | 2 | preferred |
| skill | AWS SageMaker | 1 | preferred |

Minimum relevant years: **2.0**. 4 responsibility bullets (build/validate
models, query/prepare training data, communicate model performance,
monitor/retrain).

**Ranked candidates:**

| Rank | Candidate (file) | Required | Experience | Responsibility | Preferred | Final | Label |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | Quinn Delgado — `job5_strong_match_scientist.docx` | 100.00 | 100.00 | ~90 | 66.67 | **~93.0** | Strong match |
| 2 | Harper Nakamura — `job5_degree_or_equivalent_scientist.pdf` | 100.00 | 100.00 | ~70 | 0.00 | **~79.0** | Good match |
| 3 | Micah Solano — `job5_good_gaps_scientist.pdf` | 94.55 | 100.00 | ~30 | 0.00 | **~68.6** | Possible match |
| 4 | Elliot Marsh — `job5_weak_scientist.docx` | 27.27 | 0.00 | ~6 | 0.00 | **~13.5** | Limited match |

**Reasoning:**

- **Quinn Delgado**: Python, SQL, and ML all demonstrated in bullets, exact
  master's-in-Data-Science match, well over the 2-year minimum, and 2 of 4
  preferred items (Power BI, Tableau) demonstrated. Straightforward top
  rank.
- **Harper Nakamura** (acceptance scenario 4 — degree-or-equivalent
  satisfied through years): **has no degree at all**, but the job
  explicitly allows "or equivalent experience of 4 years." With ~7 years
  of directly relevant Data Scientist experience, the education formula
  from Section 11.3 —
  `education_match = max(degree_match, min(relevant_years / stated_equivalent_years, 1.0))`
  — evaluates to `max(0.0, min(7/4, 1.0)) = 1.0`, so the education item
  scores a **full 1.00, identical to a candidate with the formal degree**.
  Required score reaches 100.00 purely through the equivalence clause.
  This candidate ranks second overall not because of any degree penalty,
  but because of zero preferred-tool overlap and a responsibility profile
  that's topically adjacent (pricing optimization) rather than an exact
  match to the job's churn/demand-forecasting framing.
- **Micah Solano**: Python and SQL demonstrated, but Machine Learning only
  appears in the skills section (never in a bullet) — capped at 0.80
  instead of 1.00 — and only 2 of the job's 4 responsibility bullets have
  any real evidence-bullet coverage (no bullet about building/validating
  models, monitoring, or retraining). No preferred items at all. This
  lands squarely in "Possible match" territory despite an on-paper strong
  background (MS Statistics, 4 years).
- **Elliot Marsh**: an honestly under-qualified profile used as the low
  end of the ranking — SQL only, no Python, no ML anywhere, a bachelor's
  in an unlisted field one level below the required master's (both the
  degree-level and field terms multiply to 0.00), and a reporting-analyst
  role that doesn't clear the role-relevance bar for "Data Scientist."
  Experience drops to 0.00 (no relevant years counted) and responsibility
  is near-zero. This is the clearest "Limited match" case in the sample
  set and should never be confused with a viable candidate.

---

## 5. Other jobs — qualitative notes only

Jobs 2, 4, and 6 have smaller, deliberately narrower candidate pools and
are not scored to the same numeric detail here; use them for targeted
behavior checks rather than full ranking fixtures.

- **Job 2 — Data Analyst II** (`job_02_data_analyst_altheadings.txt`, no
  preferred section at all): both candidates should show `preferred_score
  = None` ("N/A — not applicable"), with weights redistributed across
  required/experience/responsibility per Section 13.5 (0.45/0.85 ≈
  0.5294, 0.20/0.85 ≈ 0.2353, 0.20/0.85 ≈ 0.2353). Avery Collins (strong,
  all required demonstrated, 4+ relevant years) should clearly outrank Sam
  Whitfield (SQL demonstrated but Excel absent, exactly at the 3-year
  minimum).
- **Job 4 — BI Analyst** (`job_04_bi_analyst.txt`, no experience minimum
  stated): both candidates should show `experience_score = None`, with
  weights redistributed across required/responsibility/preferred (0.45,
  0.20, 0.15 → renormalized over a 0.80 total: 0.5625 / 0.25 / 0.1875).
  Rowan Ahmed (Power BI, SQL, Excel, and both preferred tools all
  demonstrated) should clearly outrank Emerson Blake (Power BI and SQL
  demonstrated, Excel skills-section-only, no preferred coverage).
- **Job 6 — Software Engineer** (`job_06_software_engineer.txt`, PMP is
  *preferred*, not required): Reese Chandler holds PMP ("certified 2023")
  and should receive full preferred credit for it; Finley Osei is a "PMP
  candidate" — per Section 9.6, pending credentials are **not held**
  (match value 0.00) plus a `PENDING_CREDENTIAL` warning, not a
  required-item penalty, since PMP only appears in the preferred section
  here. Both candidates should otherwise score similarly on required
  (Python, SQL, CS degree) and experience — the PMP gap should show up
  only as a small, visible dent in the preferred component, the same
  "missing one preferred item" pattern as Job 1 scenario 3, applied to a
  certification instead of a skill.

---

## 6. Acceptance-scenario cross-reference (Section 18.3)

| # | Scenario | Demonstrated by |
|---:|---|---|
| 1 | Strong candidate ranks first, "Strong match" | Jordan Ellis (Job 1), Taylor Brooks (Job 3), Quinn Delgado (Job 5) |
| 2 | Keyword-stuffer scores clearly below demonstrated-evidence candidates | Casey Nguyen (Job 1) vs. Jordan Ellis / Dakota Reyes / Morgan Patel |
| 3 | Experienced candidate missing one preferred skill → small, visible deduction only | Dakota Reyes (Job 1, missing Tableau); Finley Osei (Job 6, PMP pending) |
| 4 | "Degree or equivalent experience" satisfied through years | Harper Nakamura (Job 5) |
| 5 | Missing required license → warning, still ranked, not rejected | *(not separately fixture'd — Job 6's PMP is preferred, not required; a required-license case should be added if a future job needs one)* |
| 6 | Job without preferred quals and without experience minimum → correct redistribution, no free points | Job 2 (no preferred) and Job 4 (no experience minimum) |
| 7 | Year-only dates → scored with underestimation warning | Peyton Marsh (Job 3) |
| 8 | Same resume, name changed → identical score | *(procedural test — re-run any candidate above through the pipeline with only the name/contact block edited and diff the two `MatchResult`s; not a distinct file in this sample set)* |

**Known gap:** no synthetic resume in this batch targets a job with a
*required* certification/license, so scenario 5 (missing required
license → warning, not rejection) has no dedicated fixture yet. Add one
in a later stage if a job requiring a license (e.g., a data-role variant
requiring a specific compliance certification) is introduced.
