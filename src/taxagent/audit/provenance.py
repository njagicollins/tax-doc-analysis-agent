"""Provenance: what exactly produced a run.

The same documents can give a different result after the code, a prompt, a model
or a threshold changes. Recording all four with every run means a result can be
explained, and repeated, later.
"""

import subprocess
from pathlib import Path

from taxagent.compute.checks import TOLERANCE, VARIANCE_THRESHOLD_PCT
from taxagent.extraction.run import REVIEW_THRESHOLD
from taxagent.ingestion.raw_store import sha256_of

CODE_DIR = Path(__file__).parent
PROMPTS_DIR = CODE_DIR.parent / "agent" / "prompts"


def git(*args: str) -> str | None:
    """Ask git about the code's own repository. None when git cannot answer."""
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=CODE_DIR,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # git is not installed, or the code is not in a repository
    return done.stdout.strip()


def code_version() -> dict:
    changes = git("status", "--porcelain")  # one line per changed file
    return {
        "commit": git("rev-parse", "--short", "HEAD") or "unknown",
        # With uncommitted edits, the commit alone does not describe the code that ran
        "uncommitted_changes": None if changes is None else bool(changes),
    }


def prompt_fingerprints(prompts_dir: Path = PROMPTS_DIR) -> dict[str, str]:
    """Each prompt file with a short hash of its text.

    The file name says "v1". The hash says whether v1 still has the text it had:
    someone can edit a prompt without renaming it.
    """
    return {
        path.name: sha256_of(path.read_text(encoding="utf-8").encode("utf-8"))[:12]
        for path in sorted(prompts_dir.glob("*.md"))
    }


def provenance(models: dict[str, str]) -> dict:
    return {
        "code": code_version(),
        "prompts": prompt_fingerprints(),
        "models": models,
        "settings": {
            "review_threshold": REVIEW_THRESHOLD,
            "tolerance": str(TOLERANCE),
            "variance_threshold_pct": str(VARIANCE_THRESHOLD_PCT),
        },
    }
