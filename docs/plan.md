# Build plan

Build it end to end with a thin version of every layer first, then deepen. Phases 1–6 alone give a complete working system.

## Phase 0: Setup (½ day)
- Repo structure, `.gitignore`, `.env.example`, README stub, `docs/`
- `pyproject.toml` (uv), pytest and ruff configured
- Enable GitHub secret scanning
- Smoke-test the OpenAI key

## Phase 1: Synthetic data + mock sources (1 day)
- Generator: about 20 employees, Q1 and Q2
  - W-2 PDFs, Form 941 PDFs, payroll register Excel file
- Seeded discrepancies (these form the golden answers):
  - register wages ≠ 941 wages for Q2
  - one employee missing from the register
  - a 40% quarter-over-quarter variance explained by a bonus line
  - one low-quality/blurry PDF → low-confidence extraction
- Mock ADP FastAPI service serving the files; SQLite payroll database

## Phase 2: Ingestion (½ day)
- `taxagent ingest --quarter 2026Q2`
- Pull from the mock ADP and SQLite into write-once `data/raw/<quarter>/`
- Manifest rows: source, path, SHA-256, size, fetched_at, run_id

## Phase 3: Extraction + schema (1–2 days)
- `SourceRef` (file_sha256, page, bbox | sheet, cell)
- PDF extraction with PyMuPDF (text + coordinates); Excel extraction with openpyxl (cell addresses)
- Confidence scoring; values below the threshold go to the review queue

## Phase 4: Deterministic compute (1 day)
- Reconciliations: register vs 941, W-2 totals vs register
- Quarter-over-quarter variance with thresholds, and exception generation
- Pure functions returning `(value, [SourceRef])`, fully tested

## Phase 5: LangGraph agent (1–2 days)
- `classify → extract → validate → compute → [interrupt: review] → explain_exceptions → draft_summary → [interrupt: sign-off] → finalize`
- SQLite checkpointer, so a run can pause and resume
- Versioned prompts; citation validation; PII masking before LLM calls
- Model routing through config

## Phase 6: Streamlit app (1–2 days)
- Review queue: the value, a source-page crop with the value highlighted, accept or correct
- Exceptions: the AI explanation with citations, approve or reject
- Dashboard: reconciliation status, variances, review progress
- Sign-off with a simulated role switch that enforces maker-checker

## Phase 7: Audit + evals (1 day)
- Run metadata: input hashes, prompt versions, model names, git commit
- Audit view with "Reproduce this run"
- `evals/`: field accuracy and exception recall against the golden set

## Phase 8: Polish (1 day)
- `docker compose up` runs everything
- GitHub Actions running the tests
- README: architecture diagram, demo GIF, a "Production on Azure" section, Terraform stubs
- A 5-minute demo walkthrough

## Demo walkthrough (target)
1. `ingest`: files land with hashes; no manual upload
2. The run pauses at review: 3 low-confidence fields
3. Correct one field while viewing the highlighted source page
4. Exception: a 40% variance, with an AI explanation citing the bonus line
5. Sign-off as the same user is blocked; switch user and approve
6. Dashboard: click a number and see its evidence
7. Audit view: the lineage, then "reproduce this run"
8. Evals: accuracy against the golden set, and what it missed
