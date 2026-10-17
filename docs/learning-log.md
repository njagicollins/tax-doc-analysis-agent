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

- **Slip again:** the "Mark Phase 4 complete" commit didn't include `ENGINEERING_GUIDE.md` (edit not saved) → fixed as the first commit on the Phase 5 branch. Turn on Auto Save.

---

## Phase 5: The LangGraph agent (where AI comes in)

**What the LLM is for:** findings say **what** happened (`E007 +40%`), not **why**. An analyst would open the register, spot the $11,350 bonus line, and write the explanation. The LLM **drafts that explanation**, like a junior analyst. It may **not**: do the math (Phase 4 does), make the decision (a human does), or make claims without citing evidence (we check).

**Workflow:** classify → extract → validate → compute → [PAUSE: human reviews low-confidence values] → explain findings (LLM) → draft summary (LLM) → [PAUSE: human sign-off] → finalize.

| Idea | Meaning |
|---|---|
| **LangGraph** | workflows as a **graph** of steps (nodes) with state passed between them |
| **Interrupt** | workflow **pauses** for a human (possibly days) |
| **Checkpointer** | saves workflow state to disk (SQLite) → a paused run survives restarts |
| **PII masking** | replace names/SSNs with placeholders **before** anything reaches the LLM |
| **Citation validation** | every source the LLM cites must exist in the evidence we gave it |
| **Versioned prompts** | prompts in files (`explain_finding.v1.md`) → each run records which prompt produced which text |

**Q&A:**
- **SQLite already built?** Yes and no: Phase 1's `payroll.db` is the **mock source**; the LangGraph **checkpointer** is a different SQLite file, not built yet.
- **Could it be Redis?** Yes (LangGraph has a Redis checkpointer). SQLite = one file, nothing to run (local/single machine). Redis = separate server, faster, shared by many workers. Staying with SQLite.
- **Why mask PII even with fake data and a reputable vendor?** My answer: it's PII, it can't reach the LLM. Why:
  1. Once sent, it's out of our control (logs, backups, support tools, breaches).
  2. Law/contracts: tax data is regulated; sending SSNs to a third party can be a reportable incident.
  3. **Data minimisation:** the LLM doesn't need names to explain "E007 +40% due to a bonus".
  4. Habit: mask **always**; the day someone forgets on real data, it leaks.

### Step 1: PII masking (`src/taxagent/agent/pii.py`)
**What:** `mask(text, roster)`: names → employee IDs (`Patrick Sanchez` → `E001`), SSNs → `[SSN]`. `assert_no_pii(text, roster)`: final guard, raises `PiiLeakError` if an SSN or known name remains. 10 tests (tricky roster: "Ann Lee" inside "Ann Lee-Smith", "Joann Leeds") → **111 passed**.
**Learned:**
- Masking is a safety net on **everything** leaving for the LLM (context text can contain PII even if findings don't).
- **Pseudonymisation:** names → IDs, so the LLM can still say "E007" and humans can look it up. SSNs removed entirely (nothing needs them).
- Regex `\b` = **word boundary** ("Ann Lee" must not match inside "Joann Leeds"). `re.escape()` makes symbols in names literal. `lambda` = tiny unnamed function (sort longest name first).
- Error messages **never repeat the PII** (logs would leak it).
- Honest limit: regex only catches **known** names + the SSN pattern → production adds **NER** / Azure AI Language PII detection.
- Senior's slip: a Python edit script turned `\b` into an invisible backspace character; **ruff caught it** (another reason for a linter).
- **Why both `mask()` and `assert_no_pii()`?** My answer: mask = first layer; the guard screams if mask misses PII. ✅ Wording: guard = **detection** that blocks (prevention + detection pair again).
  - Why mask will miss someday: a bug in it; someone forgets to call it; text appended after masking; slightly different spelling.
  - = **defence in depth**: independent layers so one failure isn't a breach. The guard only works if **every** LLM call passes through it → one doorway to the LLM (next step).

### Step 2: One doorway to the LLM (`src/taxagent/agent/llm.py`)
**What:** `LLM.parse(role, instructions, prompt, schema)` is the **only** way the project talks to a model. Every call: (1) passes the **PII guard**, (2) is routed by config (`small` → `MODEL_SMALL` = gpt-4o-mini, `large` → `MODEL_LARGE` = gpt-4o), (3) returns **structured output** (a validated Pydantic object). `llm_from_env()` picks OpenAI or Azure from `LLM_PROVIDER`. 8 tests with a `FakeClient` (no real calls) → **119 passed**. Added empty `AZURE_OPENAI_*` settings to `.env.example`.

**Learned:**
- **Choke point** = one controlled entry point → no caller can forget the PII guard.
- **Structured output:** pass a Pydantic class; the model must reply with JSON that fits, validated on the way in → code reads `answer.reason`, never guesses from a paragraph.
- `instructions` = system role (how to behave); `input` = the question.
- `TypeVar T` = "you get back the type you passed in".
- `temperature=0` = pick the most likely words → less randomness, **not** a guarantee of identical answers (another reason math never lives in the LLM).
- Azure: `MODEL_*` hold **deployment names**. Switching provider = config change only (a test proves it).
- Fakes **record** what would have been sent → prove the guard blocked a call **before** anything left (`client.requests == []`). Tests stay fast, free, offline.
- `SimpleNamespace(...)` = quick object for fakes. `monkeypatch.setenv` = env var for one test only.

### 🔴 Real example: a hallucination (keep this for interviews)
One real call to `gpt-4o-mini` through the doorway, to check it works:
- **Prompt:** "E007 wages rose from 28375 to 39725 and the register shows a bonus of 11350. Why did wages rise?"
- **Answer:** `reason='Wages likely rose due to increased performance or productivity, leading to higher compensation and bonuses.'` `confident=True`
- **Correct answer:** a one-time bonus of $11,350 (28,375 + 11,350 = 39,725; regular wages unchanged).

**What went wrong:** the evidence was **in the prompt**, yet the model **invented** a cause ("increased performance or productivity") that appears nowhere in it, and said it was **confident**. This is a **hallucination**: fluent, plausible, made up.

**Why it happens:** an LLM generates the most *likely-sounding* text, not the most *supported* text. "Performance → higher pay" is a common pattern in its training data, so it fills the gap with it. Nothing in the call forced it to stick to the evidence.

**What we do about it (next steps):**
1. A proper **prompt**: use only the evidence given; say "cannot determine" rather than guess.
2. **Citations:** every claim must cite an evidence ID.
3. **Citation validation:** reject any ID not in the evidence we sent.
4. **Human approval** of every explanation; **evals** on the golden set (Phase 7).

**Question: can the model's own `confident=True` be trusted?**
- My answer: no, because it's evaluating itself.
- Deeper: its "confidence" **isn't a measurement**. It's just more generated text, produced like any other word; it checked nothing.
- Contrast with **our** extraction confidence (Phase 3): based on **checkable facts** (text layer vs scan, number cell vs typed text).
- Rule: **never trust the model's word about itself; check its work from the outside** (citations, deterministic checks, humans, evals). Same idea as my Phase 0 point: an LLM judging its own work is too generous.

### Step 3: Grounded explanations (`src/taxagent/agent/explain.py` + `prompts/explain_finding.v1.md`)
**What:**
- `gather_evidence(finding, current, previous)` → numbered facts **EV1, EV2…** from **our** extracted/computed values (each keeps its `SourceRef`s). Per kind: variance → the employee's regular/bonus/gross in both quarters; reconciliation → both totals + employee counts; missing/extra → the employee's lines. Plus the judge's own numbers (difference, percent).
- `pattern_hints()`: the **code** proves patterns (difference ÷ 9 is whole → typical of swapped digits) and hands them over as evidence. **Code computes, LLM explains.**
- Versioned prompt file: use only the evidence; cite IDs for every claim; never compute new numbers; `can_determine_cause=false` rather than guess.
- LLM returns `Explanation(claims=[Claim(text, evidence_ids)], can_determine_cause)` via the doorway (`large` model), prompt masked first.
- `validate()` checks from the **outside**: no claims; uncited claim; cites an ID we never gave; a **number not in the evidence**.
- Result records `prompt_version` + `model` (reproducibility, Phase 7).
- 8 tests with a `FakeLLM` → **127 passed**.

**Real results with gpt-4o (after the improvements):**
- **E007 variance:** "The increase in gross wages is due to a bonus of 11,350.00 in 2026Q2" [EV5, EV7]; regular wages unchanged [EV1, EV4]; `can_determine_cause=True`; **0 problems**. Compare with the earlier "increased performance" hallucination: evidence + prompt + checks fixed it.
- **Q2 typo:** "The difference of 270.00 divided by 9 results in 30.00, suggesting a possible **transposition error**" [EV5, EV6]; 0 problems.
- **Q1 missing employee:** cautious (`can_determine_cause=False`), but its evidence shows 19 vs 20 employees → points the analyst to the answer.

**Learned:**
- **Our validator had false alarms at first:** it flagged "Form **941** line **2**" as invented numbers (they're names). Checkers have **precision** too. Fix: numbers in evidence labels / the finding summary count as known.
- Iterating: run on real data → read outputs → fix evidence/prompt/validator → rerun. Prompt engineering is **empirical**.
- The prompt is a **file with a version**, so every explanation can say exactly which instructions produced it.
- Honest limit: validation catches uncited claims, unknown IDs and invented numbers, but **not** a wrong *reason* that cites real evidence → that's why a **human approves** every explanation.
- **General lesson about our own checks** (I didn't know): **our checks can be wrong too**. A validator is a check → it has **recall** (catches real problems: invented numbers ✅) and **precision** (flags only real problems: "Form 941" ❌ false alarm).
  - False alarms are dangerous: people learn to **ignore** the problems list (alert fatigue) → a real invented number goes unseen; and they look like the LLM's fault when our code was wrong.
  - Caught by **running on real outputs and reading them**. The unit tests all passed; only real data showed the flaw.
  - Fix: test checkers **in both directions** (catches bad answers **and** stays quiet on good ones); look at real outputs regularly; measure the checker's false-alarm rate in evals (Phase 7).
  - **"Who checks the checker?"** Anything that judges (validator, threshold, LLM) needs its own tests for misses **and** false alarms.

### Step 4: LangGraph workflow (`src/taxagent/agent/workflow.py` + `summary.py`)
**Graph:** START → extract → **human_review ⏸** → compute → explain 🤖 → summarize 🤖 → **sign_off ⏸** → finalize → END (⏸ = pause for a person; 🤖 = LLM drafts, never decides).
**Ideas:**
- **State** = one dict passed through the graph; each node returns only what it changed, LangGraph merges it. Must be **JSON-friendly** so the checkpointer can save it.
- **Nodes** = plain functions; **edges** = what runs next (explicit wiring = the diagram).
- **`interrupt(request)`** pauses and saves everything; **`invoke(Command(resume=answer))`** continues, even after a restart. On resume, the paused node **re-runs from its start** and `interrupt()` returns the answer.
- **`thread_id`** = the run's name in the checkpointer. Prototype proved: pause in process 1 → resume in a **fresh** process 2.
- **Structural rules in code:** review complete only when every unreadable value has a valid amount (else ask again with reasons); every finding needs accept/reject; **maker-checker** (the corrector can't sign off); no path to `finalize` except through `sign_off`.
- Nodes defined inside `build_workflow` = **closures** (they "see" the injected `llm`) → tests pass a fake.
- `summary.py`: the summary cites **finding IDs** (F1, F2).

### Code review of Step 4 (before committing) — all 4 points valid
1. **Summary lacked checks the explanations had** (numbers, no-claims) → added, reusing `numbers_in`: any number not in the text the model was shown is flagged. Summaries are where numbers get rounded/restated.
2. **Corrections recorded but never applied** ⚠️ `compute` re-read `values.jsonl`, so the reviewer's fixes never reached the math. No test caught it because no check reads W-2 fields → a **latent bug**: the audit trail would *say* "corrected by alice" while the math used the old value (the record lies).
   - Fix: `review/corrections.py` → `apply_corrections()` used by **both** compute and explain. Corrected values keep their `SourceRef`, get confidence 1.0 and **`corrected_by`** (new schema field). A correction matching nothing **fails loudly**.
   - Test uses a **spy** (a wrapper that records what `run_checks` receives). Verified the test **fails with the bug put back** and passes with the fix: a regression test is only useful if it fails on the bug.
3. **`Decimal` accepts `NaN`, `Infinity`** (and `-500`) → `amount_problem()`: must be a number, finite, and ≥ 0.
4. **Rejected runs are saved too** → correct **by design** (a rejection is a decision; auditors want it). The dashboard (Phase 6) shows only `approved`.
- **153 passed.**
- **Lesson:** review your own work like an auditor; "all tests pass" only means the tests you wrote pass. Pointing out gaps in your own system is a strong interview move.
- I asked Claude to apply the review fixes directly to my pasted files; it compared my files with its tested versions first, changed only what the fixes needed, and ran the full suite in my project (153 passed). Then I read the diff before committing.
- **Why enforce sign-off/maker-checker in code, not a procedure document?**
  - My answer: code is the only way through; it can't be bypassed. A document is just an instruction, not an implementation.
  - Plus: instructions get skipped under deadline pressure ("just this once"); code produces **evidence** automatically (who reviewed, who signed, what they decided) so auditors **verify** instead of trust; tests **prove** the control works.
  - **Weak spot:** names are typed in, so anyone can type "bob". Maker-checker is only as strong as **identity** → production uses a real login (**Entra ID**) so "bob" is Bob. Rule in code + trusted identity = defence in depth.

### Step 5: Run it for real (`agent/roster.py`, `agent/runner.py`, CLI `run` / `status` / `resume`)
**What:**
- `load_roster(quarter)`: employee ID → name from the latest payroll snapshot in the **raw zone** (our own evidence), used only for masking.
- `runner.py`: `start_run`, `run_status`, `resume_run`. Each run = a LangGraph thread (`2026Q2-<run id>`) in `data/runs/checkpoints.db`. Reading saved state never runs a step, so it needs no LLM.
- CLI stays thin: `taxagent run --quarter`, `taxagent status --run`, `taxagent resume --run ID --answer file.json`. Answers are JSON files (the UI comes in Phase 6).
- 4 new tests → **161 passed**.

**Real end-to-end run (gpt-4o), played as two people:**
1. `run` → extracted Q2 → **paused**: 6 E017 W-2 values need a human.
2. **alice** typed the 6 values (read off the scan) → resumed → compute → explain → summary → **paused for sign-off**.
3. **First run: bob rejected it.** alice had typed E017 box 6 as 427.78; the scan and payroll (213.88 + 213.88) say **427.76**. The run ended as `rejected` and was saved with bob's note. The checker caught the maker's typo: the control worked on a real mistake, not a staged one.
4. A finished run can't be resumed, so I fixed the answer file and started a **second run**.
5. **alice** tried to sign off → **blocked**: "maker-checker: alice corrected values in this run, so a different person must sign off".
6. **bob** signed off → **approved**; result saved to `data/results/2026Q2/<run id>.json`. Both results are kept: the rejected one is evidence too.
- Real summary, every claim cited, **0 problems**: "There is a discrepancy of 270.00 between the register gross wages and Form 941 line 2, possibly due to a transposition error (F1)." / "The gross wages for employee E007 increased by 40.00% due to a bonus of 11,350.00 in 2026Q2 (F2)." / "…requires a human decision to verify the potential transposition error (F1)."

**Learned:**
- Keep workflow logic in a module (`runner.py`), CLI only prints → thin shell again.
- `MakeLLM` = a **factory** (a function that builds the LLM); tests pass `fake_llm` instead of the real one.
- A finished run can't be resumed; an unknown run ID fails clearly.
- Keep answer files under `data/` (git-ignored): they contain reviewer decisions and values.
- **My pasting mistakes:** put the new `add_parser` blocks inside `run_compute_command` instead of the parser function (would crash `taxagent compute` with `NameError: commands`; tests missed it), forgot `import json`, and forgot the test imports (4 × `NameError`). Lesson: when pasting into an existing file, check *which function you're inside* — indentation decides; a `NameError` usually means a missing import.

**Known limitation: the roster is incomplete (logged, not fixed):**
- The roster comes from **one quarter's payroll database** only. So it misses: people who left since last quarter, and **ghost employees** (in the register, not in the database).
- **Why it can't leak today:** names never go into prompts. Extraction saves `employee_id`, not names; finding summaries and evidence labels use IDs. The roster is the **second** safety net (the guard); the first is not sending names at all. And only `variance` uses last quarter, which needs the person in *both* quarters, so they're in the roster anyway.
- A suggested fix, `{**load_roster(previous_quarter(q)), **load_roster(q)}`, would **crash** on the first quarter ever run (no previous snapshot) and still miss ghosts.
- **Better fix, if names ever enter prompts:** build the roster from *every* source that has names (database + register), skipping quarters that don't exist.
- Lesson: before fixing a "gap", check whether it can actually happen, and whether the fix covers the whole problem or just the case someone noticed.

**More known limitations (logged, not fixed):**
- **Connections never closed:** each `checkpointer()` opens a new SQLite connection. Fine for the CLI (the process exits, Windows closes the file). In a **long-running server** (Phase 6 UI) they'd pile up → open one at startup, close at shutdown. *Added to the Phase 6 plan.*
- **Two people answering one run at once:** both see "waiting", both resume, **last save wins**: one review silently disappears, so the evidence no longer matches what happened. Can't really happen with one CLI user; can with a web UI. Fix: **lock** the run, or **optimistic locking** (before saving, check the run is still in the state you read; refuse if not). *Added to the Phase 6 plan.*
- **`build_workflow(None, ...)`:** the hint says `llm: LLM`, we pass `None`. Safe because reading state never runs a step (and if one ever did, `None.parse` crashes loudly, not silently). A type-hint mismatch, not a bug.
- Lesson: a limitation is fine if it's **known, written down, and scheduled** for when it becomes real. Fixing everything now = building for problems you don't have yet.

- **Why run the LLM after human review, not before?**
  - I wasn't sure, so I asked. The order is **facts (human confirms) → math (code) → words (LLM)**: the LLM explains findings, findings come from math, math comes from values, so the values must be final first.
  1. **Before review some values are wrong or missing** (6 of E017's W-2 values were unreadable). LLM first = a fluent, confident explanation of a wrong result, which is worse than none because it looks trustworthy.
  2. **It would have to run twice.** Corrections change the numbers → the first explanations are stale → double cost and two versions ("which one did bob see when he signed?").
  3. **Anchoring:** the reviewer should type what the scan says, not be influenced by an AI story about the numbers.
  - **Nuance:** review makes values *confirmed by a person*, not *correct*. In run 1 alice's typo (427.78) passed review and the LLM ran on it → that's why a different person signs off **after** the LLM.
  - One sentence: the LLM runs last because it only **describes**; it should describe final numbers, not provisional ones.

**✅ Phase 5 complete.**

**Phase 5 in 60 seconds:** `uv run taxagent run --quarter 2026Q2` starts a LangGraph workflow: extract → human review ⏸ → compute → explain 🤖 → summarize 🤖 → sign-off ⏸ → finalize. Every step is saved in a SQLite checkpointer, so a run pauses for a person and resumes later, even in a new process (`status`, `resume`). The LLM only drafts: it never does the math and never decides. All calls go through one doorway that masks PII, blocks the call if any PII is left, routes the model from config and returns structured output. Every explanation and summary claim must cite its evidence, and any number that wasn't in the text the model was shown is flagged. Reviewer corrections are applied to the values before the math and keep their SourceRef plus who corrected them. Maker-checker is enforced in code: whoever corrected values can't sign off, and nothing reaches finalize without a sign-off. On a real gpt-4o run the checker rejected the first run over a typed-in typo (427.78 vs 427.76), and the second run was approved by a different person with 0 validation problems.

---

## Phase 6: The Streamlit app (a screen for the humans)

**What the app is for:** in Phase 5 the reviewer answered by writing a JSON file. Nobody in a tax team will do that. The app gives the two humans in the workflow a screen: the **reviewer** types the values the machine couldn't read, the **signer** decides on each finding and on the run. The app adds **no new rules**: every rule still lives in the workflow.

| Idea | Meaning |
|---|---|
| **Streamlit** | a Python library that turns a script into a web page; no HTML or JavaScript |
| **Rerun model** | every click reruns the **whole script** from the top; the page is redrawn from saved state |
| **Thin shell** | the app only draws and collects answers; logic stays in `runner.py` / `workflow.py` |
| **Evidence view** | the reviewer sees the **source page** next to the box they type in |
| **Least privilege** | each actor sees only what its job needs |

### Steps 1-2: Review queue with the source page (`app.py`, `review/evidence.py`, `runner.list_runs`)
**What:**
- `list_runs()`: every saved run with its status and what it waits for, newest first. The snapshot now includes the **quarter**.
- Review items carry their **`SourceRef`** (file hash, page, box), so the app can show where each value came from.
- `review/evidence.py`: `raw_file(source)` finds the stored file by its hash and **verifies the hash** before showing it; `page_image()` draws the PDF page as a picture, with a red outline around the value when its position is known.
- `app.py`: pick who you are (alice / bob / carol, a **simulated login**), start a run, pick a run, type each value beside its page. Values from the same page share one picture (E017's six boxes: one scan).
- **167 passed.**

**Learned:**
- **Rerun model:** Streamlit reruns the whole script on every interaction. So the script must rebuild the page from what is saved (the checkpointer), not from variables in memory. `st.form` collects many inputs and sends them **together** on one button press; without it, every keystroke would rerun the page. `st.rerun()` redraws after an answer is saved.
- **Thin-shell payoff:** the app calls the same `start_run` / `resume_run` / `run_status` the CLI does. No rule was copied into the app, so the CLI and the app can't disagree, and the rules are tested without a browser.
- **A changed module needs a restart.** Streamlit reloads the page script (`app.py`) by itself, but not always the modules it imports (`workflow.py`, `evidence.py`). After changing those: stop and start Streamlit.
- **PII on screen vs PII to the LLM (least privilege):** the reviewer sees the real W-2 page, name and SSN included, because the job is to read that page. The LLM gets masked text because its job (explain a variance) doesn't need names. Same data, different rule, because the **need** is different. Production: only assigned reviewers may open a page (roles from **Entra ID**), and every view is logged.
- **Pseudonymisation again:** prompts and finding summaries say `E007`, not the name. A person with access to the roster can look the name up; the LLM can't.
- **Evidence is verified before it is shown:** if the stored file no longer matches its hash, the app refuses (`TamperedFileError`) instead of showing a changed document as if it were the original.

### Step 3: Sign-off form (`app.py` `sign_off_form`, `workflow.sign_off`, `evidence.location`)
**What:**
- The sign-off **request** now carries each finding's **explanation** and **evidence**, not just its summary.
- The form shows: the AI summary, then per finding the AI explanation (labelled "a draft, not a decision") with the evidence IDs each sentence cites, an **Evidence** table (id, what, value, where), and an accept / reject choice. Then approve / reject for the whole run and a note.
- `raw_file(source)` no longer takes a quarter: it searches **every quarter's folder** by hash. `location(source)` says where a value is in words: file name, then page or cell.
- Maker-checker and missing decisions are **not** checked in the app. The app sends the answer; the workflow replies with `problems`; the app shows them in red.
- 3 new tests → **170 passed.**

**Learned:**
- **Hash lookup across quarters:** F2 compares Q2 with Q1, so its evidence includes **last quarter's** register. Looking only in the current quarter's folder would fail. Files are named by their hash, so the quarter isn't needed to find one.
- **No default decision (`index=None`):** if "accept" were pre-selected, a signer could press the button without reading: **rubber-stamping**. With nothing selected, every finding needs a conscious click, and the workflow refuses an answer with a decision missing.
- **The request is the record of what the signer saw.** `interrupt(request)` saves the request in the checkpointer. So an auditor can later see exactly what was put in front of bob when he approved. If the app fetched extra data itself at draw time, nothing would prove he was shown it. A signature only means something if you can prove **what** was signed.
  - I didn't know this one and asked. Second reason: the workflow decides **what** a signer must see, the app only decides **how it looks**, so any front end gets the same packet and it can be tested without a screen.
- **Radio buttons can't be un-selected.** I noticed that after clicking accept or reject I couldn't get back to "nothing selected" without refreshing. That's how radio buttons work everywhere, not a bug: the empty state only exists before the first click, which is all `index=None` is for.

**Manual test (2026-10-11), as alice then bob:**
- alice reviewed; alice tried to sign off → **blocked** (maker-checker) ✅
- bob left one finding undecided → **asked again** ✅
- bob decided everything → run finished ✅
- F2's Evidence table names the 2026Q1 register file ✅ (checked on run `2026Q2-20261011T164556Z-25c60351`: EV1 to EV3 point at `payroll_register_2026Q1.xlsx`, cells D10, E10, F10; EV4 to EV6 at `payroll_register_2026Q2.xlsx`). I didn't note this on the day; Claude confirmed it later from the saved run.

**Two gaps I found while testing (both fixed before the commit):**
1. **The signer couldn't see what the reviewer typed.** I typed 427.75 instead of 427.76 as alice and the run accepted it. I thought it was an edge case. It isn't: for an unreadable scan the system has **no trusted number** to compare against, so the human's value becomes the truth. A one-cent typo is too small to trip a reconciliation, so the only safety net is the second person, and bob's screen never showed alice's values.
   - Fix: review items carry `machine_value` (what the machine read, or nothing); the sign-off request carries `corrections` with that value and the `SourceRef`; the app shows a table (field, typed, machine read, typed by) **beside the source page**. `by_page()` was pulled out of `review_form` because both screens now group values by page.
   - Honest limit: this **shows** a typo, it doesn't **block** one. Bob can still not look. Stricter version: a tick per corrected value.
   - Phase 5 caught a typo like this (427.78) only because bob happened to check the scan himself. Now the screen puts it in front of him.
2. **"accept / reject" didn't say what it meant.** The AI said "possible transposition" and I agreed, so was that accept or reject? The code only stores the word.
   - Fix: captions. accept = "It is real and the evidence supports the explanation"; reject = "The finding or its explanation is wrong". approve = "The numbers can be used as they stand"; reject = "Something must be fixed first". Plus one line: accepting a finding does **not** approve the run.
   - The AI had **not** concluded: "possible transposition" and "could not tell the cause". The decision was mine. How to check it: 519,**47**5 vs 519,**74**5 has two digits swapped, and a swap always gives a difference divisible by 9 (270 = 9 × 30).
- 1 new test → **171 passed.**

**Learned from the gaps:**
- **A control is only as good as what the checker can see.** Maker-checker in code stops alice signing her own work, but it doesn't make bob's check meaningful unless her work is on his screen.
- **The machine saying "I can't read this" is a feature.** A missing value with low confidence sends the run to a human. A confident guess would have gone straight into the math.
- **A label is part of the control.** If two signers read "accept" differently, the recorded decisions can't be compared.
- **Clicking through the real app found what 170 passing tests didn't.** Tests check the rules I thought of; using it as alice and bob showed what was missing.
- **My pasting slips:** added a second `import` line instead of adding the name to the existing one (again); one blank line too many in `app.py` and one too few before the new test. `ruff check` finds mistakes, `ruff format` fixes layout: run both before committing.

### Step 3b: Four improvements I asked for after using the app (2026-10-11)
I looked at the sign-off screen and asked for: no huge blank gap, a way to reopen a finished run, more colour, and a bar chart of errors per category. The first three are done; the chart is planned for the dashboard.

**What:**
- **Cropped evidence pictures** (`evidence.py`: `last_ink`, `page_image`). The "blank gap" was not empty screen: the picture was the whole W-2 page, and the W-2 only fills the top third. Now the empty paper below the last line is cut off (E017: 1210 → 520 pixels tall).
- **Finished runs can be opened, read-only** (`workflow.sign_off_request`, `runner.record_of`, `app.show_record`). After I approved a run as bob, the app only said "Finished", so I couldn't check what F2 was about. Now a finished run shows the verdict, the note and a decision badge per finding; everything the signer saw is under one drop-down.
- **Colour with meaning** (`COLOUR`, `DOT`, `colour_of` in `app.py`; `.streamlit/config.toml`). Green = good (approved, accept), red = bad (rejected, reject), orange = waiting. Coloured dots in the run list, coloured badges for status and decisions. I chose a dark navy theme.
- 3 new tests → **174 passed.**

**Learned:**
- **A scan has no text layer**, so we can't ask the PDF where the text ends. We look at the **pixels**: go up from the bottom row by row and stop at the first row with ink. Only the bottom is cut, never the sides or top, so the red outline around a value stays in the right place. One test checks that paper is cut, another that **nothing with ink is cut**.
- **The record is rebuilt, not stored twice.** The sign-off request is made only from saved state, so the same function (`sign_off_request`) can build it again after the run is finished. The test asserts the rebuilt record **equals** what bob was shown. It also works for old runs.
- **Opening a finished run is an audit need, not a nice-to-have:** someone must be able to see later who reviewed, who signed, each decision and the evidence.
- **One colour, one meaning.** `colour_of` is the only place that decides a colour, so "green means good" can't differ between screens. Colour for decoration distracts; colour that carries status helps scanning.
- **A dark theme needs more than a background:** `base = "dark"`, light text, a slightly lighter sidebar, and a brighter button colour. The theme file is read only when Streamlit **starts**.
- **Streamlit can't put a drop-down inside a drop-down**, so inside "What the signer saw" the evidence table is shown directly (`fold_evidence=False`).
- **No new tests for colours and layout:** nothing there changes a rule or a number. Thin shell again: the look can change without touching tested logic.
- **Why the chart must wait and change shape:** categories must come from **code** (reconciliation difference, variance, unreadable scan), not from the AI's guess ("possible transposition" is not a fact). One run has 2 findings, so percentages would say 50% / 50%: show **counts**, across many runs.
- **My pasting slip, caught by ruff:** I added the new `request = sign_off_request(state)` lines but didn't delete the old block below them → `F821 Undefined name 'reviewed'`. With both blocks the run would have **paused for sign-off twice**. "Undefined name" after an edit usually means a missing import or leftover old code. I also had the error loop pasted twice in `sign_off_form`, so every error showed twice.
- For the last fixes I asked Claude to apply the changes directly; they were tested in a scratch copy first, then I read the diff before committing.

### Step 4: Dashboard and run trace (`review/dashboard.py`, `agent/trace.py`, `agent/diagram.py`, three tabs in `app.py`)
**What:**
- **Dashboard tab.** For a quarter: three headline numbers (checks passed, findings, values typed in by a person), every check with a pass/fail badge, a bar per category of what needed a person, and each finding with the signer's decision.
- **How it works tab.** Pick a run and see its **trace**: each step in the order it happened, with the tools it is built with, how long it took, what it did, and the decisions it made. "No run" shows the plain map of every step.
- `dashboard.py`: `official()` = the latest **approved** run per quarter; `check_status()`; `counts_by_category()`; `rejected_since()`. It reads `data/results`, not the checkpoint database.
- `trace.py`: `traced()` wraps every workflow step. The step returns a `"did"` sentence and optional `"notes"`; the wrapper adds the time and saves one line in the run's state.
- `ask_until_valid` now also returns the answers it refused, so they appear in the trace.
- Accept/approve are shown green and reject red (`format_func`).
- **201 passed.**

**Learned (dashboard):**
- **Numbers first, screen second.** The dashboard's figures were written and tested as plain functions before anything was drawn.
- **One official result per quarter.** I had 7 finished runs for 2026Q2; counting all of them would count the same finding 7 times.
- **Show passed checks too.** If only failures are listed, "not shown" could mean "passed" or "never ran".
- **Categories come from code, not from the AI.** "Possible transposition" is a guess; "reconciliation" and "variance" are facts the code decided.
- **Counts, not percentages**, when numbers are small: 2 findings as "50% / 50%" says nothing.
- **`Counter`** = a dictionary that counts how often each item appears.
- **`format_func`** changes what is shown, not what is stored: the saved answer is still plain `accept`.
- **Bars in one colour.** Green and red already mean good and bad in this app; a red bar would look like a judgement when it is only a count.
- **Check question I got wrong:** the latest run for a quarter is rejected and an older one was approved: what does the dashboard show? I answered about the workflow blocking. Right answer: it shows the older approved run, which is only half right, because a manager would assume all is fine. So the dashboard warns "a later run was rejected". **A dashboard must not hide bad news.**

**Learned (trace):**
- **I asked for a diagram; what I wanted was a trace.** The first version was a fixed list of steps. I said it should "follow the flow": what actually happened in a run, with time, tools and a summary per step. A **map** shows what exists; a **trace** shows what happened.
- **Each step writes its own line while the run happens**, and the line is saved with the run. Reading a trace later never re-runs anything.
- **A wrapper** (`traced`) adds timing to all 7 steps without repeating code in each one.
- **`operator.add` on the state's `trace`** tells LangGraph to add each new line to the list instead of replacing it (a **reducer**).
- **A person's step is measured by waiting time**, not work time: the gap since the previous step finished.
- **Refused answers are evidence too.** The trace caught my own first review ("alice answered and was asked again: w2.box_1 is not a number…") and alice's blocked sign-off.
- **The steps and their order are read from LangGraph** (`get_graph()`), and a test fails if a step is added without a description. A test keeps the picture honest, not a reminder.
- **Real numbers from my run (gpt-4o):** Explain 3.9 s, Summarize 1.7 s, Compute 39 ms, the rest under 50 ms. The AI is almost all of the machine time (5.6 of 5.7 s). That is where cost and delay live, and one more reason the math is done by code.

**Bugs found by looking at the real screen (not by tests):**
1. **Diagram text misaligned.** Graphviz placed the text using one font and Streamlit drew it with another. Fix: draw the steps as HTML cards, so the browser both measures and draws. Only the drawing changed; the tested data underneath stayed.
2. **"Waited 11 d 21 h".** The wait was measured from the last ingest, a separate command that ran days earlier. Fix: waits are measured only between a run's own steps.
3. **Extract shown last as "Not reached yet".** The run had started before tracing existed, so Extract had no line. Fix: such steps are shown in place as "Ran before tracing was added".
4. **Chart labels cut off.** Fix: bars drawn as rows with the full name and the number.
- Lesson: adding a feature to a system with **old saved data** needs a plan for that data (old runs have no trace). And for anything visual, a passing test proves the numbers, not the look: someone has to look.
- A module imported by `app.py` needs a Streamlit **restart**; a change in `app.py` itself only needs a refresh. I was shown the old diagram until I restarted.
- Most of these changes were applied directly by Claude after testing in a scratch copy; I checked each on screen and sent screenshots, which is how bugs 1 to 4 were found.

### Step 5: One database connection, and two people answering the same run (`agent/runner.py`, `app.py`)
**What:**
- `start_run`, `run_status`, `resume_run`, `list_runs` take an optional `saver` (the database connection). The app opens **one** with `@st.cache_resource` and passes it in every time; the CLI passes nothing and gets a new one, as before.
- Every snapshot of a run has a **`version`**: a fingerprint of where the run stands and what it is asking.
- `resume_run(..., expected=version)` refuses an answer written for an older version with `StaleAnswerError`. A lock (`ANSWERING`) makes "check the version, then continue the run" one unit.
- The app remembers which version each person was last shown (`st.session_state["seen"]`), sends it with their answer, and tells them when the run changed under them.
- 4 new tests → **205 passed.**

**Learned:**
- **Streamlit reruns the whole script on every click**, so anything created in the script is created again each time. `st.cache_resource` = "make this once, hand back the same object on every rerun". Right for connections; in a CLI the process ends, so the problem never showed.
- **Optimistic locking:** don't lock the run while someone looks at it; let everyone work, and check at the moment of saving whether the run is still as they saw it. "Optimistic" = we assume clashes are rare.
- **Lost update** = the bug it prevents: two people read the same state, both answer, and one answer silently wins or is misread. Before this step bob's late answer vanished with no message.
- **The version had to include the request, not only the checkpoint id.** Claude's first version used LangGraph's checkpoint id. Replaying two people in a test showed a gap: a **refused** answer (alice blocked by maker-checker) changes the request but not the checkpoint id. Lesson: test the scenario, not just the function.
- **Honest limit:** the lock works inside one running copy of the app. Several copies on several servers would need the check inside the database.
- **`ImportError: cannot import name 'StaleAnswerError'`** after the change: Streamlit had reloaded the new `app.py` but still held the old `runner.py`. Fix: stop and restart. Rule: only `app.py` changed → refresh; any other file → restart.
- **Tested by hand with two browser windows** (alice and bob on the same run): the second person got "This run changed since you last looked: someone else answered it." ✅

**Phase 6 in 60 seconds:** `uv run streamlit run src/taxagent/app.py` opens a three-tab app that is a thin shell over the same functions the CLI uses, so no rule lives in the screen. **Runs:** a reviewer types the values the machine could not read, beside the cropped source page, with the file's hash checked before it is shown; a second person signs off, seeing the reviewer's typed values, the AI's cited explanations and the evidence, with no default choice; a finished run opens read-only, rebuilt from saved state to show exactly what was signed. **Dashboard:** one official result per quarter (the latest approved run), every check as pass or fail, counts by category decided by code, and a warning if a later run was rejected. **How it works:** a trace of any run, step by step in the order it happened, with tools, time, what each step did and decided, including answers that were refused. One database connection serves the whole app, and an answer written for a state that has since changed is refused, so two people can't silently overwrite each other. On a real gpt-4o run the AI steps took 5.6 of 5.7 seconds of machine time.

**Two check questions I didn't know and asked for the answers:**
- **The test asserts the rebuilt record equals what bob was shown (`record[part] == seen[part]`). What if it failed?**
  - The "record" page would show something different from what the signer actually saw. Then nobody can prove what bob approved: he could say "that explanation wasn't on my screen", and we couldn't show otherwise. A signature is only worth something if you can show **exactly** what was signed.
  - It can only fail if something changes the saved state after sign-off, or if the function that builds the request stops being a pure function of that state. The test guards both.
- **Why not lock the run for alice the moment she opens the review page?**
  - That is **pessimistic locking**: assume a clash will happen and block everyone else up front.
  - Problem 1: opening a page is not a promise to finish. Alice opens it and goes to lunch, or closes her laptop: the run is stuck and bob can't help.
  - Problem 2: so you need a timeout, a way to break locks, and a way to know she is still there. A web page can't reliably tell the server "I was closed".
  - Problem 3: clashes are rare here (a few reviewers, a handful of runs), so everyone would pay that cost every time to prevent something that almost never happens.
  - Optimistic locking costs nothing until a clash really happens, and then the second person loses one click and is told why.
  - When pessimistic **is** right: clashes are frequent, or redoing the work is very expensive (editing a long document for an hour).

**✅ Phase 6 complete** (PR #9 merged).

---

## Phase 7: Audit and evals

**Why this phase:** the system worked, but couldn't answer two questions about itself. An **auditor** asks "can you prove what happened, and that nobody changed the record afterwards?" An **engineer** asks "how good is it, as a number, and did my last change make it worse?" Phase 7 answers both.

**From here on I paste all the code myself** (I asked for this at the start of the phase). Claude tests in a scratch copy first, hands over the exact code, then compares my files with the tested versions.

**Q: Is audit the same as tracing (observability)?** No.
- **Observability** = being able to tell what a running system is doing from the outside: logs, metrics (numbers over time) and traces.
- **Tracing** is for engineers: why was it slow, where did it fail. Can be sampled, kept for weeks.
- **An audit log** is for auditors: who did what and when, provably. Must be tamper-evident, complete, kept for years.
- Tracing helps you **fix** the system; the audit log lets you **prove** what happened.
- **Our observability tool** is the small trace we built in Phase 6. Tools like **LangSmith**, **Langfuse** (open source, self-hostable) or **OpenTelemetry + Azure Monitor** add every prompt and response, tokens, cost, search and alerts. Caution for tax data: a tracing tool records prompts and state, so sending it to a third-party cloud is a data decision. **I chose to add LangSmith in Phase 8.**

### Step 1: Hash-chained audit log (`audit/log.py`)
**What:** `append_event(event, actor, details)` writes one JSON line; each entry stores the **hash of the entry before it**. `verify()` returns a list of problems (empty = intact). 7 tests → **212 passed**.
**Learned:**
- Change, remove or reorder one entry and every link after it breaks.
- `entry_hash` leaves out the `hash` field itself; `sort_keys=True` makes the same entry always give the same hash.
- `verify` says **which** entry is wrong, not just True/False.
- **Limit:** entries cut off the **end** can't be noticed, because nothing after them disagrees. Fix: keep the newest hash somewhere else (`verify(last_hash=...)`).
- **Check question I didn't know (asked for the answer): how could someone with full access defeat the chain?** Change an entry and **recompute every hash after it**: no secret is involved, so the chain is valid again. The chain gives **tamper evidence**, not tamper resistance. Real protection = an outside copy of the newest hash that the writer can't change: write-once storage (e.g. Azure immutable blob storage), another team's system, or digital signatures with a key in a vault. = **separation of duties**, maker-checker applied to the log itself.
- My slip: a file that looked pasted but was empty because it wasn't saved. Watch for the unsaved dot on the editor tab.

### Step 2: Writing events (`agent/runner.py`, `cli.py`)
**What:** events `files_ingested`, `run_started`, `answer_received`, `answer_refused`, `answer_out_of_date`, `step_finished`, `run_finished`. A lock (`WRITING`) so two entries can't both follow the same entry. **214 passed.**
**Learned:**
- Write the log at the **doorway** (`start_run`, `resume_run`, the ingest command), never inside workflow steps: a paused step **re-runs from its start** when resumed, so anything written there would be written twice.
- **Record first, then act:** `answer_received` is written before the workflow uses the answer, so a crash can't erase that alice answered.
- **Attempts are logged, not only successes:** alice's blocked sign-off and bob's late answer leave entries.
- Each `step_finished` keeps the step's own `finished_at`: `at` is when the entry was **written**, which can be later. A timestamp that means something slightly different from what the reader assumes is a trap.
- Honest gap: the ingest event has no test (the command needs the mock ADP server).

### Step 3: Provenance (`audit/provenance.py`)
**What:** every run records what produced it: git commit (+ uncommitted changes), a hash of each prompt file, model names, thresholds. Saved in the run, the result file and the `run_started` audit entry. **220 passed.**
**Learned:**
- **Provenance** = where something came from. Four things can change a result: code, prompts, models, settings.
- The prompt **name** says "v1"; the **hash** proves the text is still what v1 was.
- No git on a server → "unknown", never a crash.
- **Check question, answered right:** is the model name enough to repeat a run a year later? No: the provider can update or retire the model behind the same name. Plus: pin a **dated** model name in production; and even then the model isn't word-for-word repeatable, so we **save the output**. Provenance says what produced it; the saved text proves what it said.

### Step 4: `taxagent audit` and the Audit tab (`audit/view.py`)
**What:** `taxagent audit [--last-hash ...]` verifies the log and exits with code 1 if it was changed. The Audit tab shows intact/changed, every event as one sentence, and what produced a chosen run. **233 passed.**
**Learned:**
- **Exit codes:** 0 = success, anything else = failure, so a scheduled job can react without a person reading the output.
- `match ... case` = choose what to do by the event's name.
- **My paste mistake:** replacing the last lines of `app.py` also deleted the three `with ..._tab:` blocks, so three tabs were blank, and **233 tests still passed** because no test opens the app. The thin shell is thin, not zero. (Claude now gives the whole final block for edits near the end of a file.)

### Step 5: Detection eval (`evals/detection.py`)
**What:** does the pipeline raise every planted error from `data/golden/golden.json`, and nothing else? `uv run python -m evals` → 4/4 found, **recall 100%, precision 100%**. **241 passed.**
**Learned:**
- **Test vs eval:** a test asks "does the code do what I wrote?"; an eval asks "how good is the system at its job, as a number?" and needs an **answer key**.
- **Recall** = of the real errors, how many we found. **Precision** = of the alarms raised, how many were real. You need both: flagging everything gives perfect recall and is useless.
- One planted error can cause several alarms (E013 missing → 3 findings), so each error has signals it **must** raise and side effects it **may** raise. A side effect alone doesn't count as finding the error ("smoke, not the fire").
- The eval is tested **for failing** (a missed error, a false alarm), not only passing: an eval that can't fail measures nothing. It extracts into a temporary folder: measuring must not change saved data.
- **Our 100% is like setting an exam and then sitting it:** we wrote the checks knowing the planted errors.
- **Check question I didn't know (asked): how would a real team build a trustworthy answer key?** From **past quarters already worked by hand**; labelled by people who **didn't build** the system; **two labellers** working independently, with disagreements settled by a third; **part kept hidden** for the final score (against overfitting); and every miss a person catches gets **added** to it.
- My slips: stray keystrokes `ffyghjl` in `audit/view.py` (ruff: F821 undefined name); forgot `evals/__main__.py` → "'evals' is a package and cannot be directly executed".

### Step 6: Extraction eval (`evals/extraction.py`)
**What:** is every value read exactly as its document shows it? The generator rebuilds what each document shows. Real data: 732 values, **98.4% correct, 12 unreadable** (E017's six W-2 boxes, twice), **0 confidently wrong, 0 invented**. **248 passed.**
**Learned:**
- Each eval measures one job: reading the 941 typo as printed is **correct extraction**; catching it is the checks' job.
- Not all mistakes are equal: unreadable and wrong-but-flagged go to a person (safe); **confidently wrong** flows into the math unseen (dangerous); **invented** is the worst.
- "98.4% accuracy" sounded like 1.6% wrong; in fact **none** were wrong, they were honestly unreadable. Breaking accuracy into outcomes makes the number honest.
- `Decimal(63250) == Decimal("63250.00")`: money compares by value.
- **Check question, answered right:** if a change guessed the blurry scan and got 11 of 12 right, accuracy rises to about 99.9% but the system is **worse**: "confidently wrong" goes from 0 to 1. Rule: never present a guess as a fact (a low-confidence guess still goes to a person).

### Step 7: Explanation eval (`evals/explanations.py`, `--llm`)
**What:** the real model explains each of the 5 findings **3 times**; each answer is graded right cause / honest: can't tell / too cautious / wrong cause, plus grounded, consistent, names leaked, seconds. Runs only with `--llm` (paid); the tests use the fake AI. **255 passed.**
**Learned:**
- "Honest: can't tell" is a good answer only when the evidence really can't show the cause (F1's totals, the side effects). For E007 the bonus is in the evidence, so "can't tell" is **too cautious**.
- The leak test uses a fake model built to leak: test the alarm by setting it off.
- **First real run (gpt-4o):** the three real causes found 3/3 each time; grounded 100%; 0 leaks; but the side-effect questions were only **67% consistent**, with **1 "wrong cause"**. Same question, different answers: the AI is not a function. That is why it only drafts, is checked, and a person signs.
- **Keyword grading is crude** and can be fooled both ways. Three ways to grade AI text: keyword rules (cheap), an AI judge (understands meaning, but you must trust the judge), people reviewing a sample (the reference). Teams use all three.
- **Check question, half right:** would `temperature` 0 make the explanations better? I said more consistent (right). But **consistent is not correct**: it could give the wrong answer every time, and it hides the wobble, which is a useful "I'm unsure" signal. Hosted models aren't fully repeatable even at 0.

### Step 8: Saved, comparable reports (`evals/report.py`)
**What:** every eval run is saved to `data/evals/<UTC time>.json` with its provenance and every AI answer word for word, and compared with the previous report ("Changed since the last report: ..."). Wrong-cause answers are printed in full. **262 passed.**
**Learned:**
- The useful question isn't "is it good?" but **"did my change make it better or worse?"**: that needs the old report, the new one, and what produced each.
- **An eval of text must keep the text**, so a person can check the grader.
- **Second real run:** 100% consistent, 0 wrong causes, 100% acceptable: same code, prompt and model as the first run, different scores. **An eval is itself a sample**; trust trends over several reports, not one run.
- The report recorded `uncommitted_changes: true` because I ran it before committing: provenance was honest about it. Commit first, then run, for a report you rely on.
- **My paste slip, and a weak test:** `answers = []` went **inside** the loop, so only the last answer was kept (1 per finding, not 3). All tests passed because the test asked only **once**. Fixed; the test now asks twice and checks both answers are kept. Lesson: test with the smallest case where the bug **would** show, and watch a new test fail before trusting it.
- Claude's slip: its scratch copy was wiped overnight and its file check said "matches" against files that no longer existed. Caught and rebuilt; it now checks the scratch file exists first.

**Phase 7 in 60 seconds:** every action that matters is written to an **append-only, hash-chained audit log** at the doorways (runner and CLI): who started a run, every answer (including refused and late ones), every step, every result. Editing, removing or reordering any entry breaks the chain; `taxagent audit` and the Audit tab verify it, and keeping the newest hash elsewhere also catches a log cut short. Every run records its **provenance**: code commit, prompt hashes, models, thresholds. Three **evals** measure the system against an answer key: detection (recall and precision on the planted errors: 100%/100%), extraction (98.4% read exactly, 0 confidently wrong, 0 invented), and, on request because it costs money, the AI's explanations (grounded, right cause, consistent, no leaks). Every eval run is saved with its provenance and the AI's words, and compared with the last, so the question becomes "did this change make it better?". Honest limits: the chain is tamper-evident, not tamper-proof, without an outside copy; our answer key was written by the builders; and one eval run is a sample.
