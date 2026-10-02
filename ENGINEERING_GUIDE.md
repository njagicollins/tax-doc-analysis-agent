# Engineering Guide

The goals, design rules and conventions for this project, plus where the build currently stands. See `docs/architecture.md` for the full design and `docs/plan.md` for the build plan.

## What this project is

An AI-assisted system for quarterly payroll tax analysis, designed for Azure.

The problem: corporate tax teams analyze large sets of tax documents every quarter by hand. The documents are PDFs and Excel files that live in payroll platforms such as ADP and in SaaS SQL databases. This project makes that analysis faster, more accurate and **traceable for audit**, keeps **humans in control** of every decision that matters, and requires **no manual file handling**.

The analysis being automated:

- extract figures from W-2s, Form 941s, state filings and payroll registers
- reconcile them against each other (for example, payroll-register wages vs 941 wages vs the W-2 totals)
- compare with the previous quarter
- flag variances and explain them
- produce a dashboard that analysts use to interpret the results

## Design principles (do not violate)

1. **Traceability before automation.** Every extracted or computed value carries a `SourceRef` (file SHA-256, page and bounding box, or sheet and cell). If it can't be traced, it can't be used.
2. **Determinism where it matters.** All tax math, totals, reconciliations and variances run in plain, tested Python functions. **The LLM never does math.**
3. **Human checkpoints are structural.** The AI prepares and the analyst approves. The workflow cannot finalize without a recorded human action. Maker-checker: the user who corrects a value cannot give the final sign-off.
4. **Zero-touch ingestion.** Files are pulled automatically, stored write-once and hashed.
5. **Synthetic data only.** Never commit or use real taxpayer data. SSNs and names are masked before any LLM call.
6. **Reproducibility.** Every run records input hashes, the prompt version, the model name and the git commit.

## Seven-layer architecture (summary)

1. **Ingestion:** production uses Data Factory, ADP and SQL, landing in immutable Blob storage; the local build uses a Python job pulling from a mock ADP and SQLite into `data/raw/` with a manifest.
2. **Extraction:** PDFs go through Document Intelligence (production) or PyMuPDF (local); Excel is read cell by cell with openpyxl (never OCR Excel). Each value gets a confidence score and a `SourceRef`.
3. **Normalize and compute:** a canonical Pydantic schema plus deterministic reconciliation and variance functions.
4. **AI reasoning:** a LangGraph workflow with an LLM for classification, variance explanations (with citations) and the draft summary. Uncited claims are flagged.
5. **Human-in-the-loop:** a review queue for low-confidence fields, then exception approval, then final sign-off. Implemented with LangGraph `interrupt` and a persisted checkpointer.
6. **Results and dashboard:** approved results with lineage. Production uses Power BI plus a review app; the local build uses Streamlit, with drill-through to the source page and the value highlighted.
7. **Audit, evaluation and operations:** an append-only audit log, a golden set from the synthetic "past quarter", and an evals report. Production adds Entra ID, Key Vault, Private Link and Terraform.

## Stack

Python 3.11, `uv`, Pydantic, FastAPI (mock ADP), LangGraph, `openai` SDK, PyMuPDF, openpyxl, SQLAlchemy + SQLite, Streamlit, pytest, Docker Compose, GitHub Actions.

LLM: OpenAI API (GPT-4o family). Model names come from config and are never hard-coded. Use a small model (e.g. `gpt-4o-mini`) for classification and a large model (e.g. `gpt-4o`) for explanations. The same client must be able to switch to Azure OpenAI through config.

## Adapter rule

Each Azure service sits behind an interface in `src/taxagent/adapters/` with a `local` implementation (default) and an `azure` implementation, selected by config. Going to production should be a config change, not a rewrite.

## Repo layout

```
synthetic/            data generator with seeded discrepancies
mock_sources/         mock ADP API + seed SQL database
src/taxagent/
  ingestion/          pull, hash, manifest, write-once raw zone
  extraction/         pdf.py, excel.py, confidence
  schema/             canonical models + SourceRef
  compute/            reconciliations, variance (pure functions)
  agent/              LangGraph graph, llm client, prompts/ (versioned files)
  review/             queue, approvals, maker-checker
  audit/              append-only log, run metadata
  adapters/           local/ and azure/ implementations
app/                  Streamlit: review queue, dashboard, evidence viewer, audit view
evals/                golden set + accuracy report
tests/
docs/                 architecture.md, plan.md
```

## Conventions

- Secrets live in `.env`, which is never committed; keep `.env.example` up to date.
- Prompts live in `src/taxagent/agent/prompts/` as versioned files (e.g. `explain_variance.v1.md`).
- Compute functions are pure, fully unit-tested, and return `(value, [SourceRef])`.
- Every LLM output that makes a claim must cite source IDs; validate that before accepting it.
- Favor simple, readable code over clever code.

## Current status

- [X] Phase 0: repo setup
- [X] Phase 1: synthetic data + mock sources
- [X] Phase 2: ingestion
- [X] Phase 3: extraction + schema
- [X] Phase 4: deterministic compute
- [ ] Phase 5: LangGraph agent
- [ ] Phase 6: Streamlit app
- [ ] Phase 7: audit + evals
- [ ] Phase 8: polish + demo walkthrough

Update this checklist as phases are completed.
