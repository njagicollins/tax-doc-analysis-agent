"""Eval reports: every score saved with what produced it, so two runs can be compared.

A score on its own says little. "Accuracy fell after the prompt changed" is the
useful sentence, and it needs the old report, the new one, and what changed.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from taxagent.audit.provenance import provenance

REPORTS_DIR = Path("data/evals")

# The numbers worth comparing between two reports: name -> (section, key)
HEADLINES = {
    "detection recall": ("detection", "recall"),
    "detection precision": ("detection", "precision"),
    "extraction accuracy": ("extraction", "accuracy"),
    "confidently wrong": ("extraction", "confidently_wrong"),
    "explanations acceptable": ("explanations", "acceptable"),
    "wrong causes": ("explanations", "wrong"),
    "explanations grounded": ("explanations", "grounded"),
    "names leaked": ("explanations", "leaks"),
}


def save_report(
    results: dict, models: dict[str, str], reports_dir: Path = REPORTS_DIR
) -> Path:
    """Write one report, named by the time it was made, and return its path."""
    now = datetime.now(UTC)
    report = {"run_at": now.isoformat(), "made_with": provenance(models), **results}
    path = reports_dir / f"{now:%Y%m%dT%H%M%SZ}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def latest_report(reports_dir: Path = REPORTS_DIR) -> dict | None:
    paths = sorted(reports_dir.glob("*.json"))  # names are times, so they sort
    return json.loads(paths[-1].read_text(encoding="utf-8")) if paths else None


def headlines(report: dict) -> dict[str, float | None]:
    """The comparable numbers. None where that eval was not run."""
    return {
        name: (report.get(section) or {}).get(key)
        for name, (section, key) in HEADLINES.items()
    }


def compare(before: dict, after: dict) -> list[str]:
    """One line per headline number that changed. Not run in one report: skipped."""
    old, new = headlines(before), headlines(after)
    return [
        f"{name}: {old[name]:.3g} -> {new[name]:.3g}"
        for name in HEADLINES
        if old[name] is not None and new[name] is not None and old[name] != new[name]
    ]
