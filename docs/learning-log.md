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
