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
