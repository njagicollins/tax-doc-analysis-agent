# Learning Log

A step-by-step record of how this project was built: what we did, why, and what I learned.

Each entry: **What** (commands / files) · **Why** (the reason) · **Learned** (key ideas, mistakes, gotchas).

---

## Lesson 0: The big picture

**Problem:** Every quarter, tax teams check by hand that payroll numbers agree across the payroll register (Excel), Form 941 (quarterly IRS report, PDF) and W-2s (yearly per-employee, PDF).

**Core design idea:** decide where AI goes and where it must *not* go.

| Job | Who does it | Why |
|---|---|---|
| Read numbers from files | Normal code (PyMuPDF, openpyxl) | Repeatable, traceable to page/cell |
| Math & reconciliation | Tested Python functions | Deterministic: same input → same answer |
| Explain differences | LLM, with citations | Language is its strength |
| Final decisions | A human | Accountability |

**Learned:**
- LLMs are unreliable at arithmetic, can give different answers to the same question, and can't show their working → math lives in tested code.
- SHA-256 hash = a file's fingerprint. It **detects** changes; write-once storage **prevents** them (prevention vs detection). Same hash = same file → also used to skip duplicates.
- Virtual environment = isolates a project's packages so projects don't conflict.

---

## Phase 0: Setup

### Step 0: Install uv
**What:** `curl -LsSf https://astral.sh/uv/install.sh | sh`, then reopened Git Bash → `uv --version`
**Why:** uv manages Python versions, virtual environments and packages in one tool.
**Learned:**
- **PATH** = the list of folders the terminal searches for commands. "command not found" usually means the program's folder isn't on PATH.
- A terminal reads its settings only when it starts → reopen it (or `source ~/.bashrc`) after installing tools.

### Step 1: Commit the design docs
**What:**
```bash
git add ENGINEERING_GUIDE.md docs/
git status
git commit -m "..."
git push
```
**Why:** Save the design before building anything.
**Learned:**
- Git has 3 areas: working folder → (`git add`) → staging → (`git commit`) → history.
- `git status` shows an untracked folder as one line (`docs/`); after adding, it lists each file.
- Always check `git status` before committing, to catch secrets or wrong files.
- Commit messages: imperative ("Add…", not "Added…") and accurate file names.
- `git push origin main` = send branch `main` to the remote named `origin` (GitHub). Plain `git push` works once the branch tracks a remote.

### Step 1b: Branching strategy
**What:** `git switch -c phase-0-setup`
**Why:** GitHub Flow: `main` always works; each piece of work gets a short-lived branch → pull request → merge → delete.
**Learned:**
- Git Flow (long-lived `dev` branch) vs GitHub Flow (short feature branches). We use GitHub Flow.
- `-c` = create a new branch and switch to it. Without `-c`, `switch` moves to an existing branch.
- In teams: `git switch main && git pull` before creating a branch, so it starts from the latest code.

### Step 2: Create the Python project
**What:**
```bash
uv python install 3.11
uv init --package --name taxagent --python 3.11
uv run python --version   # → Python 3.11.16
```
**Why:** Give the project a standard structure and a pinned Python version.
**Learned:**
- `pyproject.toml` = the project's ID card (name, Python version, dependencies). A standard name (PEP 518) so every tool finds it. `.toml` = a simple settings format.
- `requires-python = ">=3.11"` = the minimum supported. `.python-version` = the version uv actually uses (3.11: the most widely supported by libraries).
- uv filled in `authors` from my git config (`user.name`, `user.email`).
- `uv run` created:
  - `.venv/`: the virtual environment → **not committed** (machine-specific, rebuildable)
  - `uv.lock`: exact installed versions → **committed** (reproducible builds)
- `.venv/` didn't show in `git status` because uv puts its own tiny `.gitignore` inside it.

### Step 3: `.gitignore`
**What:** Created `.gitignore` in the project root listing: `__pycache__/`, `*.pyc`, `.venv/`, `.env`, `data/`, tool caches (`.pytest_cache/`, `.ruff_cache/`), OS/editor files (`.DS_Store`, `.vscode/`).
**Why:** Tell git which files must never be tracked: secrets, generated files, junk.
**Learned:**
- Syntax: `/` at the end = folder, `*` = anything, `#` = comment.
- Why ignore `data/` even though it's fake:
  - My answer: it can be regenerated.
  - Plus: **commit the recipe, not the output** (the generator script is the source of truth).
  - Plus: **safety habit**: in production `data/` holds real taxpayer data; ignoring it from day one prevents leaks.
  - Plus: binary files (PDF/Excel) make the repo big and slow.

### Step 4: `.env` and `.env.example`
**What:**
- Created `.env.example` (committed template: `LLM_PROVIDER`, `OPENAI_API_KEY=` empty, `MODEL_SMALL`, `MODEL_LARGE`).
- `cp .env.example .env`, then put my real API key in `.env` only.
- Checked with `git check-ignore -v .env` → `.gitignore:9:.env` (ignored by line 9).

**Why:** Secrets and settings live outside the code. Change a key or model without touching code. `.env.example` tells others which settings they need.
**Learned:**
- `.env` format: `KEY=value`, no quotes, no spaces around `=`.
- Never paste keys anywhere (chat included). Leaked key → revoke it and create a new one.
- **Gotcha:** `.gitignore` only works on files git isn't already tracking. Add the rule *before* creating the secret file.
- Why two models (**model routing**):
  - My answer: cost. Use the cheap small model for easy tasks (classification), the big one only when needed (explanations).
  - Plus: speed. Small models answer faster.
  - My extra idea: **LLM-as-judge** (one model grades another's output). Not the reason here, but useful for evals in Phase 7. The judge should be a different/stronger model; models grade their own work too kindly.

### Step 5: Folder structure
**What:**
```bash
for d in ingestion extraction schema compute agent review audit adapters; do
  mkdir -p src/taxagent/$d
  touch src/taxagent/$d/__init__.py
done
mkdir -p tests && touch tests/__init__.py
```
**Why:** Each layer gets its own place in the code, so bugs are easy to locate.
**Learned:**
- `__init__.py` marks a folder as a Python **package** → enables `from taxagent.compute import ...`.
- Bash: `for ... do ... done` loops; `mkdir -p` = make folder (no error if it exists); `touch` = create empty file; `pwd` = where am I.
- "Project root" = the main project folder.
- Git doesn't save empty folders → create `app/`, `evals/`, `synthetic/` later, when they have files.
- Folders ↔ layers:

| Layer | Folder |
|---|---|
| 1 Ingestion | `ingestion/` |
| 2 Extraction | `extraction/` |
| 3 Normalize & compute | `schema/` (data shapes, used by all layers) + `compute/` (math) |
| 4 AI reasoning | `agent/` |
| 5 Human review | `review/` |
| 6 Dashboard | `app/`, **outside** `src` (UI sits on top of core logic, swappable) |
| 7 Audit | `audit/` + `evals/` |
| not a layer | `adapters/`: swap local ↔ Azure services via config (`local/` PyMuPDF vs `azure/` Document Intelligence) |

### Step 6: pytest + ruff
**What:**
```bash
uv add --dev pytest ruff
uv run ruff check .      # → All checks passed!
```
**Why:**
- **pytest** runs tests (small functions that check code gives the right answer). Tax math must be tested.
- **ruff** is a **linter**: reads code without running it, flags mistakes and messy style. A spell-checker for code.
- `--dev` = **dev dependency**: needed while building, not to run the finished app. Went into `[dependency-groups] dev = [...]` in `pyproject.toml`.

**Learned:**
- `pyproject.toml` = what I **asked for** (a range: `pytest>=9.1.1`). `uv.lock` = what was **actually installed** (exact versions + download source + SHA-256 hash).
- Asked for 2 packages, lock has 8: pytest needs colorama, iniconfig, packaging, pluggy, pygments → **transitive dependencies** (dependencies of dependencies). The lock pins them too.
- Lock file → everyone gets identical versions → no "works on my machine" (reproducibility).
- The hashes let uv reject tampered packages (same fingerprint idea as Lesson 0).
- Commit `uv.lock`; never edit it by hand.
- `uv run <cmd>` runs a command inside the project's virtual environment.

### Step 7: First test (smoke test)
**What:** Created `tests/test_smoke.py`:
```python
import taxagent


def test_package_imports():
    assert taxagent is not None
```
Ran `uv run pytest -v` → 1 passed. Broke it on purpose (`is None`) → 1 failed. Restored it.

**Why:** Prove the project is set up correctly and Python can find our code. Every later test depends on this.
**Learned:**
- pytest finds files named `test_*.py` and functions named `test_*`. `-v` = verbose (show each test).
- `assert X` = "X must be True, otherwise fail".
- `None` = Python's "no value". `is None` / `is not None` check for it.
- **Smoke test** = simplest check that the basics work (from electronics: switch it on, see if it smokes).
- The real check is the `import` line; if the package were broken it would crash there.
- Break tests on purpose to learn to read failures.
- **ruff vs pytest:**

| | ruff | pytest |
|---|---|---|
| Runs the code? | No, just reads it | Yes |
| Catches | typos, unused imports, undefined names, style | wrong results, wrong logic |

`return a - b` instead of `a + b` → ruff says fine; only a test catches it.

### Step 8: OpenAI key check
**What:**
```bash
uv add openai python-dotenv     # normal deps (the app needs them to run)
uv run python scripts/check_openai.py
# → Model: gpt-4o-mini
# → Reply: key works
```
`scripts/check_openai.py` loads `.env` with `load_dotenv()`, creates `OpenAI()` (finds `OPENAI_API_KEY` itself), reads the model name from `MODEL_SMALL`, sends one message, prints the reply.

**Why:** Prove the chain works before building on it: `.env` → dotenv → OpenAI → model from config.
**Learned:**
- It's a **script, not a test**: tests must be fast, free and offline; this calls a paid online service → lives in `scripts/`, run by hand.
- `openai` = official library to call models; `python-dotenv` = reads `.env` into environment variables.
- **Mistake:** first run printed nothing. The file was empty (0 bytes) because I hadn't saved it. Unsaved tab = ● dot. Fix: Ctrl+S, or turn on File → Auto Save.
- Debugging rule: "no output, no error" often means the code never ran. Check simple causes first.
- **ruff has two jobs:** `ruff check` = find mistakes; `ruff format` = fix layout automatically (e.g. 2 spaces before an inline `#` comment). `ruff format --check` = report only, change nothing.

### Step 9: Commit, push, first pull request
**What:**
```bash
git add .                                  # (planned: add specific files)
git commit -m "Set up Python project with uv, pytest, ruff and OpenAI check"
# ticked Phase 0 in ENGINEERING_GUIDE.md
git commit -m "..."                        # reworded later, see below
git push -u origin phase-0-setup
git commit --amend -m "Mark Phase 0 complete in engineering guide"
git push --force-with-lease
```
Opened **PR #1** on GitHub (base `main` ← compare `phase-0-setup`), reviewed Files changed, merged.
Cleanup: `git switch main && git pull && git branch -d phase-0-setup && git push origin --delete phase-0-setup`

**Why:** GitHub Flow: work on a branch, review via PR, merge into `main`.
**Learned:**
- **Mistake:** used `git add .` → setup + learning log went into one commit instead of two. `.env` was safe thanks to `.gitignore`. `git add .` adds everything not ignored; always `git status` after it.
- Undo the last **unpushed** commit, keeping changes staged: `git reset --soft HEAD~1`.
- Git commits **changes**, not files. A file already in history still needs a new commit when edited.
- `git log --oneline` = history, one line per commit (short ID + message). The ID is a short SHA hash. `git show <id>` shows what a commit changed.
- `git push -u origin <branch>` = first push of a new branch; `-u` links it so plain `git push` works after.
- **Rewording a pushed commit:** `git commit --amend -m "..."` then `git push --force-with-lease`. `--force-with-lease` refuses if someone else pushed meanwhile (safer than `--force`). Only rewrite **your own unmerged** branch, never `main`.
- A PR doesn't finish by itself; it waits for a human to review and merge (no automatic checks until Phase 8).
- GitHub's file list shows the **last commit that touched** each file, not a file description.
- After merging: update local `main` (`git pull`), delete the branch locally (`-d`) and on GitHub (`push origin --delete`).

**✅ Phase 0 complete.**

**Phase 0 in 60 seconds:** I set up a Python 3.11 project with uv (exact versions pinned in `uv.lock`), kept secrets out of git with `.env` + `.gitignore`, created one package folder per architecture layer, added pytest (does the code work?) and ruff (is the code clean?), confirmed the OpenAI key works with the model name read from config, and merged it all through a pull request.

### After merging: cleanup and new branch
**What:**
```bash
git stash                 # shelve uncommitted edits
git switch main
git pull
git stash pop             # bring edits back
git branch -d phase-0-setup
git push origin --delete phase-0-setup
git switch -c phase-1-synthetic-data
git commit -m "Add step 9 to learning log"
```
**Learned:**
- `git switch main` failed: I had uncommitted edits to a file that didn't exist on my (outdated) local `main`. Git **refused to protect my work**, not a bug.
- `git stash` = put uncommitted changes on a temporary shelf; `git stash pop` = take them back. Pop **after** pull so the file exists first.
- `git checkout` (old, does many jobs) vs `git switch` (new, only switches branches).
- Why delete merged branches: job done, less clutter, avoid working on stale branches. Commits and the PR stay forever. `-d` refuses to delete unmerged work; `-D` forces.
- Stuck terminal escapes: Vim (`~` lines) → `Esc` then `:q!`; `>` prompt (unclosed quote) → `Ctrl+C`; `:` or `(END)` (pager) → `q`.

---

## Phase 1: Synthetic data + mock sources

**Where it lives:** `synthetic/` and `mock_sources/`, top-level, **outside `src`**. They pretend to be the outside world (employees' documents, ADP, the SQL database). In production they'd be deleted; `src/taxagent` shouldn't know it's talking to a fake.

**What we generate:** ~20 fake employees, Q1 + Q2: payroll register (Excel), Form 941 (PDF), W-2s (PDF).

**Planted errors (the golden set):**
1. Register wages ≠ 941 wages in Q2
2. One employee missing from the register
3. 40% quarter-over-quarter jump caused by a bonus
4. One blurry, hard-to-read PDF

### Why plant errors?
- My answer: to include edge cases.
- Main reason: **we know the correct answers, so we can measure the system**. Like an exam with an answer key.
  - **Recall** = did it find all the real errors? (found 3 of 4 → missed one)
  - **Precision** = were the things it flagged real errors? (false alarms lower it)
- **Golden set** = data where the correct answers are known in advance, used to measure accuracy.

### Step 1: Random seeds + Faker
**What:**
```bash
uv add faker
uv run python -c "from faker import Faker; f=Faker(); f.seed_instance(42); print(f.name(), f.ssn())"
# seed 42 → Allison Hill 229-18-1680 (same every run)
# seed 7  → Chris Curtis 075-69-1543
```
**Why:** Same seed → identical data every run → the golden answers never change (reproducibility).
**Learned:**
- **Seed** = starting number for "random" generation. Same seed = same output.
- **Faker** makes realistic fake names, SSNs, addresses: right format, not real people.
- `python -c "..."` runs a small piece of Python straight from the terminal.
- `$` prompt = Bash (git, uv, cd). `>>>` prompt = Python REPL (`uv run python` to enter, `exit()` to leave).

### Step 2: Generate employees (`synthetic/employees.py`)
**What:** An `Employee` dataclass (`employee_id`, `name`, `ssn`, `annual_salary`) and `generate_employees(count=20, seed=42)`, which uses Faker with a fixed seed. Salaries: 45,000–150,000 in steps of 500. Ran `uv run python synthetic/employees.py` twice → identical output.
**Why:** The employees are the base for every document we generate.
**Learned:**
- **Never store money as `float`**: `0.1 + 0.2` = `0.30000000000000004`. Use `Decimal` (exact).
- **SSN is a `str`, not `int`**: leading zeros (`033-04-1536` would become `33041536`), dashes, and you never do math on it. Rule: if you'd never add/average it, it's a string (phones, ZIP codes, IDs).
- It's a **fixed** seed, not a random one: the fixed starting point that makes the "randomness" repeat.
- `@dataclass` = a class that just holds data; Python writes the boilerplate.
- Type hints (`: str`, `-> list[Employee]`) say what type a value should be.
- `f"E{i:03d}"` → `E001`; `45_000` = 45000 (underscores for readability).
- `count: int = 20` = **default value**; 20 is small on purpose (enough to hide 4 errors, few enough to check by hand).
- `if __name__ == "__main__":` runs only when the file is run directly, not when imported.
- Typo in file name (`employess.py`) → renamed. Name typos cause import errors later.

### Step 3: Payroll basics (domain knowledge)
**Taxes withheld from each paycheck:**

| Tax | Rate | Notes |
|---|---|---|
| Federal income tax | depends on person | we simplify to a flat rate |
| Social Security | 6.2% | only up to the **wage base** ($176,100/year), a **maximum (cap)** |
| Medicare | 1.45% | all wages, no cap |

- Social Security + Medicare = **FICA**. The employer pays a **matching** amount on top.
- **How documents connect:** register (per employee, per quarter) → sum all employees → **Form 941**; register → sum 4 quarters per employee → **W-2**. The system reconciles these; planted errors break them on purpose.
- Worked example, $30,000 quarter: SS = 30,000 × 6.2% = **$1,860**; Medicare = 30,000 × 1.45% = **$435**; FICA withheld = **$2,295** (+ $2,295 employer match).

**Learned:**
- **Mistake:** I thought the wage base was a *minimum*. It's a **maximum**: everyone pays 6.2% until year-to-date wages pass $176,100, then SS stops for the rest of the year.
- **Medicare** (health insurance for 65+, funded by this tax) ≠ **Medicaid** (a different program).
- Our max salary ($150,000) is below the cap, so no one hits it. The code should still respect the cap: crossing it mid-year is a classic source of payroll errors.

### Step 4: Generate quarterly payroll (`synthetic/payroll.py`)
**What:**
- Added `synthetic/__init__.py` (makes `synthetic` a package → `from synthetic.employees import ...`).
- `PayrollLine` dataclass: `employee_id`, `quarter`, `regular_wages`, `bonus`, `gross_wages`, `federal_tax`, `ss_tax`, `medicare_tax`.
- `generate_payroll(employees, quarters)`: regular wages = annual salary ÷ 4; federal 12% (simplified); SS 6.2% respecting the $176,100 cap; Medicare 1.45%.
- **Planted error #3** as named constants at the top: `E007` gets a 40% bonus in `2026Q2`.
- Ran with `uv run python -m synthetic.payroll`.

**Result:**
- E001: Q1 $31,625 → Q2 $31,625 (stable, normal).
- E007: Q1 $28,375 → Q2 $39,725 (bonus $11,350 = exactly 40%). ✅ planted error works.

**Learned:**
- `money()` rounds to cents with `ROUND_HALF_UP` (0.005 → 0.01, the accountant's way; Python's default rounding differs).
- `ss_wages_so_far` is a **dictionary** `{employee_id: amount}` tracking year-to-date SS wages → how the cap works.
- `x if condition else y` = one-line if/else.
- Planted errors live in **named constants**, not buried in logic, so they're obvious to readers.
- `python -m package.module` runs a file as a module from the project root, so package imports work.
- **`Decimal` quotes rule:** whole numbers → `Decimal(0)` (exact, no quotes needed). Fractions → **must** quote: `Decimal(0.1)` inherits float error; `Decimal("0.1")` is exact. ruff flagged `Decimal("0")` (FURB157) → fixed with `ruff check --fix`.
- Missing `__init__.py` still "worked" (Python **namespace packages**), but add it anyway: tools like pytest can get confused, and it keeps the project consistent.
- **Slipped through:** `scripts/check_openai.py` reached `main` unformatted. I'd run `ruff check` (mistakes) but not `ruff format --check` (layout); they're different commands. Real fix = automation: GitHub Actions runs checks on every PR (Phase 8).

### Checkpoint commits
- Committed in 3 small pieces, naming files explicitly: format fix / generators (+ `pyproject.toml` + `uv.lock` for faker) / learning log.
- **Mistake:** only 1 of 3 commits happened at first (I hadn't run `ruff format`, so there was nothing to commit). Always confirm with `git status` / `git log`: check what *actually* happened.
- `LF will be replaced by CRLF` warning = Windows vs Mac/Linux line endings; harmless.
- Commit each small working step, so there's always a known-good point to return to.

### Step 5: Payroll register in Excel (`synthetic/register.py`)
**Design decision:** separate the planted errors so each problem has **one cause**:

| # | Error | Quarter | Planted in | Caught by |
|---|---|---|---|---|
| 1 | Register ≠ 941 (typo in 941) | Q2 | 941 PDF | reconciliation (same quarter, 2 documents) |
| 2 | E013 missing from register | Q1 | Excel register | reconciliation |
| 3 | E007 40% bonus jump | Q2 | payroll data | variance (between quarters) |
| 4 | Blurry PDF | any | one W-2 | low extraction confidence |

#3 isn't really an *error*: the bonus was genuinely paid. The system flags it as **unusual**; the explanation makes it acceptable. Telling "wrong" from "unusual but valid" is the analyst's job.

**What:** `uv add openpyxl`; `write_register()` writes `data/sources/adp/payroll_register_<quarter>.xlsx`: title row, blank row, headers on row 3, one row per employee, bold TOTAL row, money format `#,##0.00`. Skips E013 in Q1 (**planted error #2**, named constants).
**Result:** Q1 has 19 employee rows (E013 missing); Q2 has all 20.
Sanity check: Q2 total $519,475 − Q1 total $470,625 = $48,850 = $37,500 (E013's missing quarter) + $11,350 (E007's bonus). ✅

**Learned:**
- `-m` = run as a **module** (dotted name, not a file path). Python starts looking from the project root, so `from synthetic.employees import ...` works. With a file path it starts inside `synthetic/` → `ModuleNotFoundError`.
- `Path`: modern file paths, works on any OS; `folder / "file.xlsx"` joins them. `mkdir(parents=True, exist_ok=True)` = create folders, no error if they exist.
- **List comprehension**: `[x for x in items if condition]` = filtered list in one line.
- `getattr(line, "bonus")` = `line.bonus`, with the field name from a variable.
- Real Excel exports have titles, so headers aren't on row 1; the extractor must handle that.
- On Windows, an Excel file open in Excel is **locked** → close it before rerunning (else `PermissionError`).
- **Excel has no Decimal type**: numbers come back as `int`/`float`. Phase 3 must convert them back to `Decimal` carefully.
- ruff format: lines max 88 characters. Run `ruff check` + `ruff format` before every commit.

### Step 6: Form 941 PDF (`synthetic/form941.py`)
**Domain:** the 941 = the company's quarterly report to the IRS. Lines we use: 1 (employee count), 2 (wages), 3 (federal tax withheld), 5a (SS wages × **12.4%**), 5c (Medicare wages × **2.9%**), 5e (5a + 5c tax), 6 (total taxes = 3 + 5e).
- 12.4% / 2.9% because the 941 reports **both halves**: employee share + employer match.

**What:**
- Added `ss_wages` to `PayrollLine` (line 5a needs it; we computed it but threw it away). Designs evolve.
- `uv add pymupdf` (writes PDFs now, reads them in Phase 3).
- `compute_941()` sums **all** payroll lines (including E013); `write_941()` draws the form with PyMuPDF → `data/sources/adp/form_941_<quarter>.pdf`.
- **Planted error #1:** `transpose_digits()` swaps two digits on Q2 line 2: real 519,475.00 → typed **519,745.00**.

**Results:**

| Comparison | Numbers | Explained by |
|---|---|---|
| Q1: 941 vs register (reconciliation) | 508,125 − 470,625 = **37,500** | #2 E013 missing from register |
| Q2: 941 vs register (reconciliation) | 519,745 − 519,475 = **270** | #1 typo |
| 941: Q2 vs Q1 (variance) | 519,745 − 508,125 = **11,620** | #3 bonus 11,350 **+** #1 typo 270 |

**Learned:**
- **Transposition trick:** swapped digits → the difference is always divisible by 9 (270 ÷ 9 = 30).
- **Reconciliation** = same quarter, different documents. **Variance** = same document, different quarters.
- The typo **hides inside** the variance: looking at variance alone, all 11,620 looks like bonus. Only reconciliation exposes the 270. That's why each error needs a separate cause and why we run both checks.
- **Mistake:** I compared 941 Q1 vs 941 Q2 instead of 941 Q1 vs register Q1. The register total is in the Excel TOTAL row, Gross Wages column.
- PDF coordinates: `(x, y)` in **points** (1/72 inch) from the **top-left**; US Letter = 612 × 792. These positions become the bounding box in `SourceRef` later.
- `f"{value:,.2f}"` → `519,745.00` (thousands commas, 2 decimals).
- `assert` in code as a safety check: if the swap changed nothing, stop loudly instead of silently planting nothing.

### Step 7: W-2s + blurry scan (`synthetic/w2.py`)
**Design problem:** a W-2 covers a full year; we only have Q1 + Q2. **Simplification:** W-2s are built from Q1 + Q2 only ("year-to-date"). Written down in the code. Rule: simplifying is fine if you **document** it ("we simplified X because Y; in production Z").

**W-2 boxes:** 1 wages · 2 federal tax · 3/4 SS wages/tax (6.2%) · 5/6 Medicare wages/tax (1.45%). Each must match the sum of the employee's register rows.

**What:** `compute_w2()` sums an employee's payroll lines; `draw_w2()` writes the form → `data/sources/adp/w2_2026_<id>.pdf` (20 files).
**Planted error #4:** E017's W-2 is turned into a 40 DPI image (`get_pixmap(dpi=40)` → `insert_image` into an empty PDF) = a fake low-quality scan.
**Result:** 24 files total (2 registers + 2 941s + 20 W-2s). E001 is clear; E017 is blurry and unreadable.

**Learned:**
- **Text layer vs scan:** a normal PDF stores real characters with positions → PyMuPDF reads them exactly (selectable with the mouse). A scan is only **pixels** → PyMuPDF finds **zero** text, even if the scan is sharp.
- **OCR** (Optical Character Recognition) guesses characters from pixels. Blur makes OCR guess wrong (8 vs 3) → **low confidence** → human review.
- Design: **text layer → trust it; scan → OCR + confidence → human checks low-confidence values.** Production: Azure Document Intelligence does OCR with per-field confidence.
- **DPI** = dots per inch; normal scan 200–300, ours 40 (blurry on purpose).

### Step 8: One command + golden answer key (`synthetic/__main__.py`)
**What:**
```bash
rm -rf data/                 # start from nothing
uv run python -m synthetic   # → 24 source files + data/golden/golden.json
```
`golden.json` lists the 4 planted errors with expected values: #1 difference `270.00` (true 519,475.00 vs reported 519,745.00), #2 E013 `37500.00`, #3 E007 `40.00`%, #4 `w2_2026_E017.pdf`. Matched my hand checks exactly.

**Why:**
- One command → a new teammate doesn't need to know the order of scripts.
- `__main__.py` inside a package runs on `python -m <package>`.
- Answer key is **computed from the same constants** that plant the errors → **one source of truth** (change the bonus → the key updates).
- Answer key lives in `data/golden/`, **apart from** `data/sources/`: the system must never see the answers.

**Learned:**
- `rm -rf data/` deletes only the **output**. The errors live in the **code** (recipe), committed in git. Fixed seed → rebuilt identically.
- Deleting and rebuilding proves the command builds **everything** from nothing (no leftover file hiding a missing step).
- `rm -rf` has **no undo**: double-check the path.
- Docstring `"""..."""` explains a file/function. `str | None = None` = "a string or nothing" (optional argument).
- JSON has no Decimal → store money as strings. `json.dumps(obj, indent=2)` = readable JSON.

### Step 8b: Turn the hand-check into tests (`tests/test_synthetic.py`)
**What:** 3 tests: same seed → same employees (dataclasses compare with `==`); golden values are exactly 270.00 / 37500.00 / 40.00 / E017; typo difference `% 9 == 0`. `uv run pytest -v` → **4 passed**.
**Learned:**
- If you check something by hand, ask: **should this be a test?** A test repeats the check forever and catches someone breaking it later.
- Tests go **one file per topic** in `tests/`; pytest finds every `test_*.py`.
- Test the **calculations**, not file writing → fast tests.
- `%` = modulo (remainder). `x % 9 == 0` = divides evenly by 9.

### Step 9: Mock ADP API (`mock_sources/adp_api.py`)
**Concepts:**
- **API** = how one program asks another for something over the network (restaurant: you → waiter/API → kitchen/data).
- **Endpoints** = the menu: `GET /documents` (list files), `GET /documents/{name}` (download one). GET = give me; POST = send; DELETE = remove.
- **Status codes:** 200 OK · 401 not logged in · 404 not found · 422 badly formed request.
- **FastAPI** = where you write endpoints. **uvicorn** = the server that listens on a port and passes requests to FastAPI.
- `127.0.0.1` = **localhost** (this computer, not reachable from the internet); `8000` = the **port** (door number).

**Why a fake server instead of reading the folder?**
- My answer: in production the docs come from ADP (and SaaS SQL) over the network.
- Plus: real-world problems appear early (logins, 404s, server down), so ingestion isn't naive.
- Plus: swapping to real ADP = change the URL + key in config, not the code (adapter idea).

**What:**
```bash
uv add fastapi uvicorn
uv run uvicorn mock_sources.adp_api:app --reload   # keep this terminal open
# browser → http://127.0.0.1:8000/docs
```
- `.env.example`: `ADP_BASE_URL=http://127.0.0.1:8000`, `MOCK_ADP_API_KEY=` (**empty**). `.env`: real value.
- Tested in the `/docs` page: with key → **200** + list of 24 files; no/wrong key → **401 Unauthorized**.

**Learned:**
- `@app.get(...)` = **decorator**: attaches the function to a URL.
- `Header()` reads request **headers** (`x_api_key` → `X-API-Key`). `Depends(check_api_key)` runs the check before every endpoint. `HTTPException(401)` = reply with an error.
- **Path traversal:** asking for `../../.env` to escape the folder and steal secrets. Defence = only serve names from an **allow-list**.
- **Security habit (my question):** `.env.example` is committed → even a harmless key shouldn't go there. Rule: names + harmless defaults (URLs, model names) only; anything granting access stays **empty**.
- **Fail loudly:** `os.environ["KEY"]` crashes at startup if missing; `os.environ.get("KEY", "dev-key")` silently used a hidden default key. Crash > silent default.
- `ERR_CONNECTION_REFUSED` = nothing listening on that port → the server isn't running. A server lives only as long as its terminal; use a **second terminal** for other commands.
- Swagger "Server response" = what actually happened; "Responses" = documentation of possible codes.
- E017 scan = 452,364 bytes vs ~3,437 for text W-2s (~130×): images are big → size hints a PDF is a scan.
- Both 941s are 4,661 bytes despite the typo (swapping digits keeps the length) → **size proves nothing about content; a hash does**.

### Step 9b: Tests for the server (`tests/conftest.py`, `tests/test_mock_adp.py`)
**What:** `uv add --dev httpx2`; 6 tests: missing key → 401, wrong key → 401, list → 200, download → exact bytes, unknown file → 404, path traversal (`..%2F..%2F.env`) → 404. `uv run pytest -v` → **10 passed**.
**Learned:**
- **`TestClient`** sends requests to the app **inside Python**: no uvicorn, no port, no browser → fast. The running server isn't needed (a busy terminal just can't take commands → Ctrl+C or open a second terminal).
- **`conftest.py`** runs before tests; gives tests their own key (`os.environ.setdefault`) because the server fails loudly without one.
- **Fixture** (`@pytest.fixture`) = reusable setup; a test gets it by naming it as a parameter.
- **`tmp_path`** = fresh empty temp folder per test. **`monkeypatch`** = temporarily swap a value (pointed `DOCUMENTS_DIR` at the temp folder), restored after.
- `b"..."` = **bytes** (raw file content). `%2F` = `/` inside a URL.
- Tests must not need `.env` or `data/` → they pass on **any machine** (fresh clones, CI).
- **Regression test** (I didn't know this one): the traversal test passes today, but protects the **future**. If someone "simplifies" the code and removes the allow-list, the test fails before the bug reaches `main`. Rule: when you fix a bug or add a protection, add a test that proves it; the test also documents *why* the code exists.
- **Caught before commit:** `.env.example` still had `MOCK_ADP_API_KEY=dev-key`. Review `git diff` before committing.
- **…and it got committed anyway.** Fix = a new commit emptying the value. With a **real** secret, a new commit isn't enough (it stays in history) → **revoke the key** immediately.

### Step 10: Payroll SQL database (`mock_sources/seed_db.py`)
**Concept:**
- **Database** = tables of rows/columns built for programs; queried with **SQL**.
- The DB is the **system of record** (complete, correct). The Excel register is an **export** from it, and the export dropped E013. So the DB **includes** E013.
- **SQLite** = a whole database in **one file**, no server; built into Python (`import sqlite3`). Stands in for the SaaS SQL DB.

**What:**
- Tables: `employees` (id, name, ssn, salary) and `payroll` (one row per employee per quarter) → `data/sources/sql/payroll.db`.
- Added `seed_database(employees, lines)` to `synthetic/__main__.py` → one command still builds everything.
- `tests/test_seed_db.py`: 20 employees / 40 payroll rows; E013 Q1 present (3,750,000 cents); quarter totals. → **13 passed**.

**Result / reasoning:** DB Q1 total = 50,812,500 cents = **$508,125** = the 941, not the register ($470,625) → the **register is the wrong document**.
- Refinement: "2 of 3 agree" is a **strong hint, not proof** (two sources can share the same mistake). The system suggests; the **analyst confirms** (human-in-the-loop).

**Learned:**
- **Money as integer cents** in the DB ($37,500.00 → `3750000`): SQLite has no exact decimal. `to_cents()` asserts there are no fractions of a cent.
- **`?` placeholders**, never glue values into SQL text → prevents **SQL injection** (e.g. a "name" of `'); DROP TABLE employees; --`).
- **Schema** = table design. **PRIMARY KEY** = unique row ID (`(employee_id, quarter)` → no duplicates). **REFERENCES** = **foreign key** (payroll row must point to a real employee).
- `commit()` = save permanently. `try/finally` → `finally` always runs → connection always closed (Windows locks open files).
- SQL basics: `SELECT ... FROM ... WHERE ...`, `COUNT(*)`, `SUM(...)`, `GROUP BY`, `ORDER BY`.
- ruff sorts imports alphabetically (I001) → `ruff check --fix`.

**✅ Phase 1 complete.**

### Phase 1 wrap-up (PRs #2 and #3)
- **My first summary missed things:** Phase 1 built test **data** (not tests); the 941 vs register conflict is the *effect* of the missing employee, not a separate error; I forgot #4 (blurry scan), the seed, the golden key, the 13 tests, security, and money handling.
- **Mistake:** PR #2 merged without the `.env.example` fix and the Phase 1 tick. The edits weren't saved → `git add` on an unchanged file does **nothing, silently**, and the commit message claimed a change that wasn't there. Fixed in a follow-up branch + PR #3.
- Rule: before committing, `git status` must list **every file you expect**.
- Stuck in `git diff` → it's the pager → press `q`.

**Phase 1 in 60 seconds:** I built a fake "outside world" with a fixed seed so it's identical on every run: 20 employees, Q1/Q2 payroll, an Excel register, Form 941 PDFs, W-2 PDFs, a mock ADP API (key auth, path-traversal safe) and a SQLite payroll database. I planted 4 errors (missing employee, transposed digits, 40% bonus, blurry scan) and generated a golden answer key from the same constants, kept apart from the sources. Tests lock in the answers, the API security and the database contents.

---

## Phase 2: Ingestion

**Goal:** one command (`uv run taxagent ingest --quarter 2026Q2`) fetches every document from ADP and the SQL DB, and stores it **safely with proof**. Zero-touch: no manual downloads.

```
Mock ADP API ─┐
              ├─→ fetch → hash (SHA-256) → save to data/raw/<quarter>/ → manifest row
SQLite DB  ───┘
```

| Idea | Meaning | Why |
|---|---|---|
| **Raw zone** | `data/raw/<quarter>/`: untouched copy of what we received | Evidence; all later steps work from it |
| **Write-once** | a stored file is never overwritten | proves the analyzed file = the received file |
| **Manifest** | one row per file: source, path, SHA-256, size, fetched_at, run_id | the receipt for auditors |
| **run_id** | unique ID per ingestion run | "which run brought this file in?" |

- Code now lives in `src/taxagent/ingestion/`: the **real product** for the first time (Phase 1 was the fake world).
- Branch: `git switch -c phase-2-ingestion`

### Design question: re-running ingestion when 1 of 24 files changed
- My answer: unchanged files stay as they are (the hash detects duplicates); the changed file doesn't overwrite the original but sits **next to it** as a new version → **lineage** and future audits.
- Refinements: the hash **detects** the duplicate, the code **decides** to skip it (prevention vs detection). A changed document is itself a **finding** (amended 941?) → alert the analyst; every analysis records **which version** it used.
- Design = **content-addressed storage**: file name starts with its hash (`3f2a9c1b7d4e_form_941_2026Q2.pdf`). Same content → same name → skip. New content → new name → keep both.

### Step 1: Raw store (`src/taxagent/ingestion/raw_store.py`), built test-first
**What:** `store_raw(content, name, quarter)` saves bytes to `data/raw/<quarter>/<hash[:12]>_<name>`, read-only, never overwriting. Returns a frozen `StoredFile(path, sha256, size_bytes, is_new)`. 6 tests in `tests/test_raw_store.py` → **19 passed** total.

**TDD (test-driven development):** write tests first → run → watch them **fail** (`ModuleNotFoundError`) → write code until they pass. Tests = the specification.

**How `store_raw` decides:**
- `path.exists()` → "have we seen this **content** before?" (the hash is in the name). No → save, `is_new=True`.
- Yes → re-hash the file **on disk**: `!= digest` → "has our stored copy been **tampered** with?" Match → `is_new=False` (skip). Mismatch → `TamperedFileError`.
- A new version never reaches the tamper check: different content → different path.

**Learned:**
- `hashlib.sha256(b).hexdigest()` = 64 hex chars; 12 in the file name, all 64 in the manifest.
- `open("xb")`: `x` = exclusive create (fails if the file exists) → write-once enforced by Python itself.
- `chmod(0o444)` = read-only. `frozen=True` dataclass = can't be changed after creation (a receipt shouldn't be editable).
- Own error type `class TamperedFileError(Exception)` → callers can catch that specific problem.
- Names from outside are untrusted → reject any name containing a path (path traversal again).
- `with pytest.raises(X):` = the code inside **must** raise X → how you test that something is blocked.
- **Mistake:** I thought `chmod(0o644)` in the test was about making files immutable. It's the opposite: the test plays the **attacker** and undoes read-only in one line.
- → **Read-only is a speed bump, not a wall** (prevents accidents only). The **hash check detects** any edit, however it was done. Production: Azure **immutable blob storage (WORM, Write Once Read Many)**, where even admins can't change files until retention ends.

### Step 2: Manifest (`src/taxagent/ingestion/manifest.py`)
**What:** `ManifestRow` (run_id, source, name, path, sha256, size_bytes, is_new, fetched_at); `new_run_id()`, `make_row()`, `append_row()`, `read_rows()` → `data/raw/manifest.jsonl`. 4 tests → **23 passed**.
**Learned:**
- **JSON Lines (`.jsonl`)** = one JSON object per line. Append new rows at the end, never rewrite old ones (fits an append-only audit log); a crash only affects the last line.
- `open("a")` = **append** mode.
- **UTC** everywhere: one clock for all servers; convert to local time only for display.
- `run_id` = UTC timestamp (readable, sorts by time) + random **UUID** piece (unique even within the same second): `20260927T154217Z-f87b63f1`.
- `asdict(row)` dataclass → dict; `ManifestRow(**d)` dict → dataclass (`**` unpacks a dict into keyword arguments).
- `as_posix()` → paths always with `/` (same manifest on any OS). Always pass `encoding="utf-8"` on Windows.
- **Why log `is_new: false` rows** (I didn't know): "nothing changed" is a fact worth recording. With only new files logged, *missing evidence* and *evidence of no change* look the same. Logging every fetch proves "on Oct 5 we checked again and the 941 was unchanged".

### Step 3: ADP source (`src/taxagent/ingestion/sources.py`)
**What:**
- Mock API: `GET /documents?quarter=2026Q2` returns that quarter's docs **plus that year's annual docs** (W-2s), each with a `period`. Parsed from the name with a **regex**.
- `DocumentSource` **Protocol** + `AdpApiSource.fetch_documents(quarter)` → list of `(name, bytes)`.
- `httpx2` moved from dev to a real dependency (the product now makes HTTP calls).
- Tests: `test_sources.py` (quarter filtering, wrong key fails loudly) + updated `test_mock_adp.py` → **26 passed**.

**Learned:**
- **Protocol** = an interface/contract ("has `name` + `fetch_documents(quarter)`"). Any class following it plugs in → ADP, SQL, Azure are interchangeable (adapter idea in code). `...` = shape only, no body.
- **Dependency injection:** `AdpApiSource(..., client=...)`. Tests pass FastAPI's `TestClient` → the real client code is tested against the real mock server with **no network**.
- Real APIs filter on the **server** (query parameter `?quarter=`), not by sending everything.
- **Regex:** `\d{4}` = 4 digits, `(?:Q[1-4])?` = optional quarter, `(...)` = capture. **Bug caught by tests (in the senior's draft!):** "starts with digits" matched `941` → period "941". A precise pattern fixed it. Tests catch everyone's mistakes.
- Changing the API broke an old test → good: forced a deliberate update, not an accidental one.
- `raise_for_status()`: 401/404 → Python error. **Without it** (my answer): the error page gets saved as a "W-2" → hashed, read-only, in the manifest as legitimate evidence; the failure surfaces days later in extraction, far from the cause. = **silent failure**. Crash where the problem happens.
- `timeout=30` → never wait forever on a dead server.
- **Import groups** separated by blank lines: standard library → third-party → our own code (ruff I001).

### Step 4: SQL source (`SqlPayrollSource` in `sources.py`)
**What:** Query the quarter's payroll (JOIN employees for name/SSN) → CSV snapshot `payroll_db_<quarter>.csv` as `(name, bytes)`. 3 tests → **29 passed**.
**Why:** A database holds rows, not files. Exporting a snapshot means the DB's data at that moment is hashed and preserved like the PDFs.
**Rules in the code:**
- **Read-only connection** (`file:...?mode=ro`): ingestion must never change source systems. Enforced by the connection, and a test plays the attacker (swaps the query for a DELETE → must fail).
- **Deterministic export:** fixed columns, `ORDER BY`, `lineterminator="\n"` → byte-identical CSV each run → hash only changes when data does (otherwise a fake "new version" every day).
- **JOIN** = pull matching rows from another table (like Excel VLOOKUP). `payroll AS p` = table **alias**.

**Learned:**
- `(quarter,)` = one-item **tuple**; `(quarter)` is just brackets. Classic gotcha.
- `[(name, content)] = ...` unpacks **and** asserts exactly one item.
- `cursor.description` → column names. `io.StringIO()` = in-memory file. Python's csv defaults to `\r\n` line endings.
- **Why both sources matter** (I didn't know): from outside they're **identical** (`name` + `fetch_documents(quarter)` → `(name, bytes)`); all differences are hidden inside. The pipeline loops over any source without asking which one → new source = one new class; production = swap the source; tests = a tiny fake source. **Code against the shape, not the details.**

### Step 5: Pipeline (`src/taxagent/ingestion/pipeline.py`)
**What:** `ingest(quarter, sources)` loops over **any** sources → `store_raw` → `append_row` → classifies each document as **new**, **unchanged** or **changed** (same name, different content = a finding for the analyst). Returns `IngestResult(run_id, new, unchanged, changed)`. 3 tests with a `FakeSource` → **32 passed**.
**Learned:**
- **Fake / test double:** `FakeSource` follows the same shape as ADP/SQL → the pipeline accepts it → instant tests, no server, no DB. The payoff of the Protocol.
- `*sources` = collect any number of arguments into a tuple.
- `glob(f"{'?' * 12}_{name}")`: `?` = exactly one character → finds **any version** of a document. Look for earlier versions **before** storing (else you find the file you just saved).
- `field(default_factory=list)` → each result gets its **own** list. `= []` would make all results share one list (**mutable default** trap).
- **Why 2 manifest rows but 1 file** (I didn't know; it's Step 2's idea again): the raw store records **content** (each unique doc once); the manifest records **events** (every fetch). 1 file proves no duplicates; 2 rows prove the second run left evidence of "checked, unchanged". Regression test for the audit trail.
- Learning tip: when stuck, ask "**which earlier idea is this?**" Core idea here: **store content once, log every event**.

### Step 6: The `taxagent ingest` command (`src/taxagent/cli.py`)
**What:**
- `pyproject.toml` → `[project.scripts] taxagent = "taxagent.cli:main"` (this line creates the command). Emptied `src/taxagent/__init__.py`.
- Settings: `ADP_API_KEY`, `PAYROLL_DB_PATH` (product side). The server keeps `MOCK_ADP_API_KEY`. Locally both keys are `dev-key`; in production only `ADP_API_KEY` exists → no code change.
- `tests/test_cli.py` (5 tests via `parametrize`) → **37 passed**.
- Real run (server in terminal 1, command in terminal 2):
  - Run 1: `23 new, 0 unchanged, 0 changed`
  - Run 2: `0 new, 23 unchanged, 0 changed` → manifest has **46 rows**.

**Why 23 files?** ADP has 24; Q2 skips the two Q1 docs (941 + register) → 22 (Q2 941, Q2 register, 20 annual W-2s) + 1 SQL snapshot CSV = **23**. Proves the quarter filter works.
**Why the 2nd run found nothing new:** same ADP files + byte-identical CSV (deterministic export) → same hashes → nothing stored, but 23 more manifest rows (store once, log every event). Without `ORDER BY` we'd get a false "1 changed" every run.

**Learned:**
- The product must never say "mock": neutral setting names so production is config-only.
- **argparse** = built-in commands/options; **subcommands** (`ingest`) leave room for `extract`, `review`… (like `git commit`).
- `type=quarter_arg` validates at the door; regex `^...$` = the **whole** text must match (`2026Q5` rejected).
- `main(argv=None)`: real runs read the terminal, tests pass a list (dependency injection).
- `except httpx2.ConnectError` → one clear sentence instead of a 40-line traceback. Still fails (exit code 1), just **readably**.
- The `sources = [...]` list is the **only** place that knows the concrete sources.
- `@pytest.mark.parametrize` = run one test for many inputs.
- Switch VS Code terminals: dropdown / list in the terminal panel, or Ctrl+PageUp/PageDown.

### Commit order mistake
- **Mistake:** I committed the CLI without the sources/pipeline commits → that commit **imported files not in git** → broken if checked out.
- Rule: **every commit should work on its own** (any point in history can be checked out and tested).
- Fix (unpushed, so safe): `git reset --soft HEAD~1` (undo last commit, keep changes staged) → `git restore --staged .` (unstage all, files stay changed) → re-commit in **dependency order**: sources → pipeline → CLI → log.
- Verified: each commit passes on its own (29 → 32 → 37 tests).

**✅ Phase 2 complete.**

**Phase 2 in 60 seconds:** `uv run taxagent ingest --quarter 2026Q2` pulls every document for a quarter from the ADP API and the SQL database (exported as a deterministic CSV snapshot). Each file is stored write-once and read-only, named by its SHA-256 hash (content-addressed), so duplicates are skipped, changed documents are kept side by side and flagged, and tampering is detected on re-runs. Every fetch is logged in an append-only JSONL manifest with a run ID and UTC timestamp. Sources hide behind one Protocol, so production is a config change, and 37 tests (using fakes, no network) lock it all in.

---

## Phase 3: Extraction + schema

**Goal:** turn raw files into numbers the system can check, each carrying **proof of where it came from**.

| Idea | Meaning |
|---|---|
| **`SourceRef`** | a value's address: file hash + (page + bounding box) for PDFs, or (sheet + cell) for Excel. Principle #1: *can't be traced → can't be used* |
| **Confidence** | 0–1: how sure we are. Text layer ≈ certain; scan with no text = 0 |
| **Canonical schema** | one standard shape for every extracted value, whatever file it came from |

- `SourceRef` uses the **file hash, not the name**: names repeat across versions; a hash points to exactly one version, forever.
- **Pydantic** = like a dataclass but **validates** data on creation (confidence 0–1, page ≥ 1…). Bad data rejected at the door.

### Which is easier to reference precisely: PDF or Excel?
- **Mistake:** I guessed PDF. It's **Excel**.
- Excel has **built-in structure**: every value lives at an exact cell (`Register!F4`); openpyxl gives value + address together.
- A PDF is just "draw text X at position (x, y)". It doesn't know "line 2" exists → we **infer**: find the label, take the number on the same line, record its coordinates. Layout changes can break the guess.
- A scan has no text at all → nothing to point to without OCR.
- → Guide rule **"never OCR Excel"**: don't throw away precision the file already has.

| | Excel | PDF (text) | PDF (scan) |
|---|---|---|---|
| Address | exact cell, built in | coordinates, inferred | none without OCR |
| Confidence | very high | high | low / zero |

### What is a schema?
- A **fixed template** every piece of data must fit (like a shipping label: the warehouse reads the label, not the contents; missing fields → rejected).
- 941 PDF, W-2 PDFs, Excel register, SQL CSV are all different, but once extracted they **all look the same** → the math never asks "PDF or Excel?". Same trick as the `DocumentSource` Protocol: many inputs, one shape.
- **Canonical** = the one official version.

### Step 1: Schema (`src/taxagent/schema/models.py`)
**What:** `uv add pydantic`. `SourceRef` (file_sha256 + page/bbox **or** sheet/cell) and `ExtractedValue` (field, value, confidence, source). 9 tests → **46 passed**. The test names read as a plain-English list of rules.
**Learned:**
- `BaseModel` = Pydantic's dataclass with validation. `Field(ge=0, le=1)` = ≥ 0 and ≤ 1. `Field(pattern=...)` = must match a regex (64 hex chars = real SHA-256).
- `@model_validator` = a rule over **several fields together**: PDF page **or** sheet cell, never neither/both (`in_pdf == in_sheet` catches both bad cases).
- `frozen=True` → evidence can't be edited after creation. `Self` = "returns this same class".
- **`None`, not `0`, for unreadable values:**
  - My answer: 0 is still a number usable in arithmetic; None clearly says "no number here".
  - Plus: E017 as 0 → W-2 totals **silently wrong** → false mismatch hunted for hours, or a wrong report. As None → `Decimal + None` → `TypeError` → math **refuses** → code is forced to send it to a human first.
  - Rule: **"unknown" must look different from every real value** ($0 is a real amount).

### Step 2: Excel extractor (`src/taxagent/extraction/excel.py`)
**What:**
- Schema: added `employee_id: str | None` to `ExtractedValue` (register values belong to an employee; 941 values to the company).
- `extract_register(path, file_sha256)` → one `ExtractedValue` per money cell, with `SourceRef(sheet, cell)`. Finds the header row itself; skips blank + TOTAL rows; ignores name/SSN.
- 10 tests (built on a real register from the synthetic generator) → **56 passed**. Q1: 19 employees × 6 columns = 114 values, E013 absent, E001 gross = 31,625.00 at `F4`.

**Learned:**
- `to_money()` handles "Excel has no Decimal" (from Phase 1): numbers go **via `str()`** so float errors don't sneak in (`458.56` stays exact).
- **Confidence** = "how much should we trust this value?", not only "did we read it right?". Real number cell = 1.0; number typed **as text** = 0.9; unreadable = `None` / 0.0.
- Why text gets 0.9 (my answer: probably typed by a human). Plus: Excel's `=SUM()` **skips text cells** → the file's own total can silently disagree with itself. Likely right, worth a look → a threshold (e.g. 0.95) sends it to review.
- `MONEY_COLUMNS` maps the file's header names → our canonical names (ADP renames a column → change one line).
- `data_only=True` = read formula **results**, not formula text. `cell.coordinate` = `"F4"`.
- The file hash is **passed in**, not recomputed: the raw store already knows it (no duplicate work, no chance to disagree with the manifest).
- **Set** `{...}` = no duplicates (114 values → 19 employees).
- Robustness test: insert 2 rows at the top → extractor still works and reports the **new** cell (`F6`). Exports change.
- **Commit slip again:** Step 1 wasn't committed before Step 2 → committed both in dependency order.

### Step 3: PDF extractor (`src/taxagent/extraction/pdf.py`)
**What PyMuPDF sees:** no fields, just words with boxes, e.g. `(460.0, 156.2, 515.0, 171.3) '519,745.00'` = (left, top, right, bottom) in points.
**Strategy:** group words into rows by bottom edge (`round(y1)`) → find the row containing a label → take the numbers on that row → their boxes become the `SourceRef`. Label never found → `None` / 0.0. **Never guess.**
**Results:** 941 Q2 line 2 = **519,745.00** (typo, read as printed); line 5a has 2 columns (wages 519,475.00 + tax); E007 W-2 box 1 = **68,100.00** (Q1 + Q2 + bonus); E017 scan → all 6 boxes `None`/0.0, ID from file-name hint. 5 tests → **61 passed**.
**Learned:**
- `numbers[-len(fields):]` = the **last** N numbers on the row (skips the line number, e.g. `2`; line 5a takes 2).
- Confidence **0.98**: characters exact (text layer), but which label they belong to is **inferred** from position. Excel = 1.0 (cell address certain).
- Every expected field always comes back (found or `None`) → review knows exactly what's missing.
- The **ID printed on the form beats the file name** (the form is evidence, the name is metadata). Hint only used when the form is unreadable.
- `scope="module"` fixture = built once per test file. `_` = "don't need this". `*_` in a loop ignores extra items.
- **Why the extractor returns the wrong number** (I asked for a simple explanation): the extractor is a **witness, not a judge**. It reports exactly what the document says; reconciliation (Phase 4) decides if it's right. If extraction "fixed" typos → the error disappears, a wrong form goes unnoticed, and the `SourceRef` would point at a box that says something else (a lie). **One job per part**: extraction copies faithfully, checking is someone else's job.

### Step 4: SQL snapshot extractor (`src/taxagent/extraction/csv_snapshot.py`)
**What:** `extract_payroll_snapshot(path, file_sha256)` → one value per cents column, divided by 100 (`3750000` → `37500`, exact with `Decimal`). Confidence 1.0. CSV has no cell names → build Excel-style addresses (column 7, row 2 → `G2`). Fields prefixed `payroll_db.` so every value says which document it came from. 2 tests → **63 passed**.
**Learned:**
- `enumerate(reader, start=2)` = count while looping (row 1 is the header). `next(reader)` = take just the first row.
- `dict(zip(header, row, strict=True))` pairs names with values; `strict=True` crashes on a wrong column count instead of silently dropping data.
- `get_column_letter(7)` → `"G"` (borrowed from openpyxl).
- The test builds the CSV the **same way ingestion does** (`SqlPayrollSource`) → proves what ingestion produces, extraction can read.
- **Mistake:** `ImportError` → the file was **empty (not saved)**, third time. That's also exactly TDD's "watch it fail" error. Fix: turn on **File → Auto Save**.
- **Why extract the SQL snapshot if the register "has the same data"?** (I wasn't sure; I'd answered it in Phase 1 Step 10.)
  - With 2 documents that disagree (941 $508,125 vs register $470,625) you can't tell which is wrong.
  - With 3: 941 = SQL = $508,125, register = $470,625 → register is the odd one out, and E013 is in SQL but not the register.
  - = **triangulation**: an independent third source identifies which of two is wrong (the analyst still confirms).
  - "Should contain the same data" is an **assumption**; our job is to **check** assumptions (exports drop rows, copies go stale).

### Step 5: `taxagent extract` (`src/taxagent/extraction/run.py`)
**What:**
1. Reads the manifest → **latest version** of each document for the quarter (`latest[(source, name)] = row`: later rows overwrite earlier ones).
2. **Re-checks each file's hash against the manifest** before reading → never extract from tampered evidence (`TamperedFileError`).
3. Picks the extractor **by document name** (simple **rule-based classifier**; Phase 5's LLM will classify unknown ones). Unknown document → error, never silently skipped.
4. Saves all values to `data/extracted/<quarter>/values.jsonl` (Pydantic `model_dump_json()` / `model_validate_json()`).
5. Lists values below **0.95** confidence for human review.
- Real run: **369 values** (register 120 + 941 9 + W-2s 120 + SQL 120); **6 need review, all E017** → planted error #4 caught automatically. **71 passed**.

**Learned:**
- `data/raw/` = **evidence** (never overwritten). `data/extracted/` = **derived data** (rebuildable from raw → safe to overwrite; improve the extractor, just re-run).
- **Integration test:** real generator + real ingestion + real extractors together; only the server is replaced (`FolderSource`). `monkeypatch.chdir(tmp_path)` = temporarily change working folder.
- Two `parametrize` decorators = **every combination** (2 commands × 4 bad quarters = 8 tests).
- `{text:<22}` = pad to 22 characters, left-aligned.
- **"Address already in use" (port 8000):** an old copy of the server was still running. Two programs can't share one port. Use the running one, or stop it (Ctrl+C in its terminal, or `Stop-Process -Id <PID>` / `taskkill //PID <PID> //F`). PIDs change each start.
- **Why only E017 was flagged:**
  - My answer: not an extraction failure; it's computation/reconciliation's job.
  - Refinement: not a failure of **anything**. Phase 4 isn't built yet.
  - **Confidence measures the *reading*, not the *document*.** The typo was read correctly (0.98): the document is wrong, our reading is right. A missing row can only be noticed by comparing sources. The bonus is only visible between quarters.

| Question | Owner | Our errors |
|---|---|---|
| Did we **read** it correctly? | Extraction (confidence) | #4 blurry scan ✅ |
| Is the **document** correct? | Reconciliation + variance (Phase 4) | #1, #2, #3 |

**✅ Phase 3 complete.**

**Phase 3 in 60 seconds:** `uv run taxagent extract --quarter 2026Q2` turns every stored document into values in one canonical Pydantic schema, each with a `SourceRef` (file hash + page and bounding box for PDFs, sheet and cell for Excel/CSV) and a confidence score. Excel and CSV are read cell by cell (never OCR'd, confidence 1.0); PDFs are read by finding each label and the numbers on the same row (0.98, because the match is inferred); scans have no text, so their values are `None` with confidence 0, never guessed. Files are re-hashed against the manifest before reading, and anything below 0.95 goes to human review, which caught the blurry W-2 automatically. The extractor reports documents exactly as printed; judging them is Phase 4's job.

---

## Phase 4: Deterministic compute (the judge)

**Goal:** compare extracted values → **exceptions** (problems an analyst must look at). Every result carries the `SourceRef`s of every value it was built from.

| Check | Compares | Catches |
|---|---|---|
| **Reconciliation** | same quarter, different documents (941 vs register vs SQL) | #1 typo, #2 missing employee |
| **Variance** | same document, different quarters (Q1 vs Q2) | #3 bonus jump |

**Ideas:**
- **Pure function**: output depends **only** on inputs (no files, network, clock, randomness) → same inputs, same answer = **deterministic**. Why the LLM never does math.
- **Traced amount**: a number that carries its evidence; adding numbers combines their evidence. Guide rule: compute returns `(value, [SourceRef])`.
- **Tolerance**: how big a difference counts as a real mismatch. **Threshold**: how big a quarter-over-quarter change is "unusual" (e.g. 25%).

### Tolerance question
- **My answer:** $0 → more escalations (high recall, low precision). $1,000 → miss genuine errors below $1,000 (low recall, higher precision).
- Specifics: $1,000 would **miss #1** (the $270 typo). $0 → **penny false alarms**: SS tax rounded per employee (20 roundings) vs the 941 multiplying the total once → a few cents apart with no error (real Form 941 has line 7, "fractions of cents").
- Tolerance depends on the check: wages = exact sums (tight); taxes = rounding along the way (small cushion).
- We use **$1.00**. Thresholds are **business decisions**, tuned on real data. Analysts care more about **recall** (never miss a real error) than precision (a few extra alerts).

### Step 1: Traced amounts (`src/taxagent/compute/traced.py`)
**What:** `Traced(value, sources)`; `traced(extracted)` and `total(values)`, which add values **and keep every source**. Unreadable value → `UnreadableValueError("w2.box_1 for E017 could not be read")`. 4 tests → **75 passed**.
**Learned:**
- The `None` lesson pays off: our own clear error (what + who) instead of Python's vague `TypeError`.
- `pytest.raises(..., match="E017")` also checks the error **message**. Useful errors say what and where.
- `sum(..., Decimal(0))`: second argument = **starting value** (default is int `0`).
- Nested comprehension `for p in parts for s in p.sources` flattens a list of lists.
- Test helpers (`value(...)`) keep tests short.
- **Why a tuple, not a list** (my answer: list is mutable, tuple immutable). Concretely: `frozen=True` blocks `t.sources = []` but **not** `t.sources.append(fake)` or `.clear()` → evidence could be silently faked or deleted. Tuples have no `append`/`clear`.
- Lesson: **"frozen" is only as strong as its weakest part**; freezing the box doesn't freeze its contents (same shape as "read-only is a speed bump").

### Step 2: Reconciliation + variance (`src/taxagent/compute/checks.py`)
**What:**
- `reconcile(check, left, right, tolerance=1.00)` → `Reconciliation(difference = right − left, matches = |difference| <= tolerance)`. Planted typo: 519,475 vs 519,745 → difference **270.00**, mismatch.
- `variance(check, previous, current, threshold_pct=25)` → `Variance(change, change_pct, flagged = |pct| > 25)`. Planted bonus: 28,375 → 39,725 = **+40.00%**, flagged.
- 11 tests → **86 passed**.

**Learned:**
- **Boundary testing:** bugs live at edges (`<` vs `<=` is a one-character bug) → test just below, exactly at, just above, and negative.
- `abs()`: −$270 is as wrong as +$270; a 50% drop is as unusual as a rise.
- **Division by zero:** change from $0 has no percentage → `change_pct = None` ("unknown ≠ 0" again), but still **flagged** for a human (new hire? missing row last quarter?).
- Results keep the whole verdict (both sides + evidence + difference + decision) → Phase 5's LLM explains exceptions from exactly this, citing `sources`.
- Constants at the top **and** parameters with defaults → business can tune, tests can override.
- **Edges (my answer):** exactly 25% → **not** flagged (`>`); exactly $1.00 → **match** (`<=`). ✅
- **Why decide on purpose:** must match written policy ("over 25%" = `>`); auditors ask "why wasn't 25.00% flagged?"; same answer every quarter (determinism); tests lock it so changes are deliberate. Rule: whenever you write `<` or `<=`, ask **"what happens exactly at the line?"** and put it in a test.

### Step 3: Findings on real data (`src/taxagent/compute/findings.py`)
**What:** `run_checks(quarter, current, previous=None)` → list of `Finding` (kind, check, quarter, summary, employee_id, difference, change_pct, sources). Four checks: register vs 941; register vs payroll DB; employee lists (missing **and** extra/"ghost"); variance per employee (only with a previous quarter). 4 tests on **real generated + extracted** data → **90 passed**.
**Results:**
- **Q1:** 3 findings, all **$37,500**: register vs 941, register vs DB, E013 missing → planted **#2** ✅
- **Q2:** exactly 2 findings: register vs 941 **$270** → **#1** ✅; E007 **+40.00%** → **#3** ✅

**Learned:**
- **Finding** = analyst's "exception"; we avoid the word in code (Python `Exception` = error).
- **Ghost employee** = paid in the register but not in the system of record: a classic payroll-fraud pattern.
- Set operations on keys: `a.keys() - b.keys()` (in a, not b), `a.keys() & b.keys()` (in both). `sorted()` → stable order every run.
- Each check does one job: variance skips employees missing from a quarter (the employee-list check reports them) → no double alarm.
- `summary` is written by **code** (deterministic, exact numbers); the LLM (Phase 5) only explains.
- `typo, bonus = findings` asserts **exactly 2** → an extra false alarm fails the test (tests **precision**, not just recall).
- `tmp_path_factory` = module-level `tmp_path`; `pytest.MonkeyPatch.context()` = temporary change inside a `with` block. `{x:+}` = always show the sign.
- **One error → three findings, a problem?** My answer: no, the 3 findings let the analyst identify the missing row immediately. ✅ (They confirm each other: same $37,500, one names E013 = triangulation.)
  - Cautions: **alert fatigue** (dozens of alerts → skimming → missed errors) → **group** related findings as one problem (Phase 5 can help).
  - **Count errors, not alerts** in evals (Phase 7): 3 findings for #2 = **one** error caught.

### Step 4: `taxagent compute` (`src/taxagent/compute/run.py`)
**What:** Loads `data/extracted/<quarter>/values.jsonl` (+ the previous quarter's, if extracted, for variance) → `run_checks` → saves `data/findings/<quarter>/findings.jsonl` → prints each finding. 11 tests → **101 passed**.
**Real run (both quarters):**
```
2026Q1: 3 findings (no previous quarter → variance skipped)
  [reconciliation] Register 470,625.00 vs Form 941 line 2 508,125.00: difference 37,500.00
  [reconciliation] Register 470,625.00 vs payroll database 508,125.00: difference 37,500.00
  [missing_employee] E013 is in the payroll database (37,500.00) but not in the register
2026Q2: 2 findings (compared with 2026Q1)
  [reconciliation] Register 519,475.00 vs Form 941 line 2 519,745.00: difference 270.00
  [variance] E007 gross wages 28,375.00 -> 39,725.00 (+40.00%)
```
**All 4 planted errors caught:** #4 in extraction; #1, #2, #3 in compute.

**Learned:**
- `previous_quarter` edge case: 2026Q1 → **2025Q4** (year boundary).
- `TypeAdapter(Finding)` → Pydantic saves/loads a plain dataclass (with Decimals + SourceRefs) as JSON.
- **Helpful errors** say what's wrong **and** how to fix it ("Run: taxagent extract --quarter 2026Q2").
- Fast tests with tiny hand-made data (3 values) show exactly what's being tested.
- **Why `run_checks` never touches files** (I didn't know): calculator vs filing clerk.
  1. **Testing:** hand it a list → instant; otherwise every test must write folders + JSONL first.
  2. **Reuse:** the agent (Phase 5) and app (Phase 6) pass values from memory/DB/Azure, not our files.
  3. **Production:** moving to Azure changes only the clerk (`run_compute`); the tax math stays untouched and tested.
  4. **Determinism:** no hidden inputs (files can be missing, half-written, changed).
  - Pattern = **"pure core, I/O shell"**: important logic pure in the middle; reading/writing/network in a thin outer layer (sources fetch, raw store writes, extractors + checks transform).

**✅ Phase 4 complete.**

**Phase 4 in 60 seconds:** `uv run taxagent compute --quarter 2026Q2` is the judge. It runs pure, deterministic Python checks over the extracted values: reconciliations (register vs Form 941, register vs payroll database, employee lists including ghost employees) with a $1.00 tolerance, and quarter-over-quarter variance per employee with a 25% threshold. Every number is a traced amount that carries the SourceRefs of every value it was built from, unreadable values make the math refuse rather than guess, and edge cases (exactly $1.00, exactly 25%, division by zero, Q1 → previous year) are decided on purpose and locked in by tests. On real data it catches the typo ($270), the missing employee ($37,500, named E013) and the bonus (+40%). With the blurry scan caught in extraction, all four planted errors are found. No LLM touches the math.
