"""The dashboard's numbers: one official result per quarter, summarised.

Reads only finished runs saved in data/results. Everything here is a plain
function over those saved results, so every number on the dashboard can be
tested without a screen.
"""

import json
from collections import Counter
from pathlib import Path

from taxagent.agent.workflow import RESULTS_DIR
from taxagent.compute.checks import VARIANCE_THRESHOLD_PCT

# Every check the judge runs, in words a reviewer would use
CHECKS = {
    "register_vs_941_wages": "Register wages match Form 941 line 2",
    "register_vs_payroll_db_wages": "Register wages match the payroll database",
    "payroll_db_vs_register_employees": "Register and payroll database list the same people",
    "quarter_over_quarter_gross_wages": (
        f"Nobody's wages moved more than {VARIANCE_THRESHOLD_PCT}% since last quarter"
    ),
}

# Categories come from the code that made the finding, never from the AI's guess
CATEGORIES = {
    "reconciliation": "Totals don't match",
    "missing_employee": "Missing from the register",
    "extra_employee": "Not in the payroll database",
    "variance": "Large change since last quarter",
}
TYPED_IN = "Unreadable value typed in by a person"


def load_results(results_dir: Path = RESULTS_DIR) -> list[dict]:
    paths = sorted(results_dir.glob("*/*.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def official(results: list[dict]) -> dict[str, dict]:
    """For each quarter, the latest approved run: the one result that counts."""
    latest = {}
    for result in sorted(results, key=lambda r: r["run_id"]):  # run ids sort by time
        if result["status"] == "approved":
            latest[result["quarter"]] = result
    return latest


def rejected_since(results: list[dict], chosen: dict) -> list[dict]:
    """Rejected runs of the same quarter made after the official one.

    Someone looked again and said no, so the official numbers may be out of date.
    The dashboard must say so, not hide it.
    """
    return [
        result
        for result in results
        if result["quarter"] == chosen["quarter"]
        and result["status"] == "rejected"
        and result["run_id"] > chosen["run_id"]
    ]


def check_status(result: dict) -> list[dict]:
    """Every check with pass or fail, so a clean check is shown, not just absent."""
    failed = Counter(item["finding"]["check"] for item in result["findings"])
    return [
        {
            "check": label,
            "result": "fail" if failed[name] else "pass",
            "findings": failed[name],
        }
        for name, label in CHECKS.items()
    ]


def counts_by_category(result: dict) -> dict[str, int]:
    """How many things needed a person, by category. Counts, not percentages."""
    counts = Counter(CATEGORIES[item["finding"]["kind"]] for item in result["findings"])
    typed_in = len(result.get("corrections", []))
    if typed_in:
        counts[TYPED_IN] = typed_in
    return dict(counts)
