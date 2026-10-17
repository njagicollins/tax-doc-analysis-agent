"""Detection eval: does the pipeline find every planted error, and raise nothing else?

The answer key (data/golden/golden.json) lists the errors planted in the synthetic
data. This compares it with what extraction and the checks really raise. No AI and
no person takes part, so the score is the same every time it runs.
"""

import json
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from taxagent.compute.findings import run_checks
from taxagent.extraction.run import ExtractionResult, run_extraction
from taxagent.schema.models import ExtractedValue

GOLDEN_PATH = Path("data/golden/golden.json")


@dataclass(frozen=True, order=True)
class Signal:
    """One thing the pipeline raised, or should have raised."""

    quarter: str
    kind: str
    check: str
    employee_id: str | None = None


def expected(error: dict, quarters: list[str]) -> tuple[set[Signal], set[Signal]]:
    """What a planted error MUST raise, and what else it MAY raise as a side effect."""
    match error["type"]:
        case "reconciliation_mismatch":
            return {Signal(error["quarter"], "reconciliation", error["check"])}, set()
        case "missing_employee":
            quarter, employee = error["quarter"], error["employee_id"]
            check = "payroll_db_vs_register_employees"
            must = {Signal(quarter, "missing_employee", check, employee)}
            # One person missing from the register also throws both wage totals off
            may = {
                Signal(quarter, "reconciliation", "register_vs_941_wages"),
                Signal(quarter, "reconciliation", "register_vs_payroll_db_wages"),
            }
            return must, may
        case "variance":
            check = "quarter_over_quarter_gross_wages"
            quarter, employee = error["to_quarter"], error["employee_id"]
            return {Signal(quarter, "variance", check, employee)}, set()
        case "low_confidence_document":
            # w2_2026_E017.pdf -> E017
            employee = Path(error["document"]).stem.split("_")[-1]
            return {Signal(q, "needs_review", "w2", employee) for q in quarters}, set()
    raise ValueError(f"No rule for planted error type {error['type']!r}")


def raised(
    quarter: str, result: ExtractionResult, previous: list[ExtractedValue] | None
) -> set[Signal]:
    """Everything the pipeline flags for one quarter: findings and values to review."""
    findings = run_checks(quarter, result.values, previous)
    signals = {Signal(f.quarter, f.kind, f.check, f.employee_id) for f in findings}
    for value in result.needs_review:
        document = value.field.split(".")[0]  # "w2.box_1" -> "w2"
        signals.add(Signal(quarter, "needs_review", document, value.employee_id))
    return signals


def score(errors: list[dict], signals: set[Signal], quarters: list[str]) -> dict:
    """Compare what was planted with what was raised.

    recall: of the planted errors, how many were found.
    precision: of the things raised, how many a planted error explains.
    """
    rows, explained = [], set()
    for error in errors:
        must, may = expected(error, quarters)
        missing = must - signals
        explained |= (must | may) & signals
        rows.append(
            {
                "id": error["id"],
                "type": error["type"],
                "cause": error["cause"],
                "found": not missing,
                "missing": [asdict(signal) for signal in sorted(missing)],
            }
        )
    unexpected = signals - explained
    return {
        "errors": rows,
        "unexpected": [asdict(signal) for signal in sorted(unexpected)],
        "recall": sum(row["found"] for row in rows) / len(rows),
        "precision": len(explained) / len(signals) if signals else 1.0,
    }


def run_detection(golden_path: Path = GOLDEN_PATH) -> dict:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    quarters = sorted(golden["quarters"])

    signals: set[Signal] = set()
    previous = None  # the first quarter has nothing to be compared with
    with tempfile.TemporaryDirectory() as scratch:  # an eval must not touch saved data
        for quarter in quarters:
            result = run_extraction(quarter, extracted_dir=Path(scratch))
            signals |= raised(quarter, result, previous)
            previous = result.values
    return score(golden["planted_errors"], signals, quarters)
