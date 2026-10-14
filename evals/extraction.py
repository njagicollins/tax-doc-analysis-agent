"""Extraction eval: is every value read exactly as its document shows it?

The synthetic generator wrote the documents, so running it again tells us what
each one shows, planted errors included: the 941 typo is printed on the form, so
reading the typo is CORRECT extraction. Catching it is the checks' job, not this.
"""

import tempfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from synthetic.employees import generate_employees
from synthetic.form941 import compute_941
from synthetic.payroll import QUARTERS, generate_payroll
from synthetic.register import MISSING_EMPLOYEE_ID, MISSING_QUARTER, MONEY_FIELDS
from synthetic.w2 import compute_w2
from taxagent.extraction.run import REVIEW_THRESHOLD, run_extraction
from taxagent.schema.models import ExtractedValue

Key = tuple[str, str, str | None]  # (quarter, field, employee_id)


def printed_values() -> dict[Key, Decimal]:
    """What every document shows, rebuilt with the same code that wrote it."""
    employees = generate_employees()
    lines = generate_payroll(employees)

    shown = {}
    for line in lines:
        on_register = (line.employee_id, line.quarter) != (
            MISSING_EMPLOYEE_ID,
            MISSING_QUARTER,
        )
        for name in MONEY_FIELDS:
            amount = getattr(line, name)
            shown[(line.quarter, f"payroll_db.{name}", line.employee_id)] = amount
            if on_register:
                shown[(line.quarter, f"register.{name}", line.employee_id)] = amount
    for quarter in QUARTERS:
        for name, amount in compute_941(quarter, lines).items():
            shown[(quarter, f"form_941.{name}", None)] = amount
        for employee in employees:  # every quarter reads the same W-2s
            for name, amount in compute_w2(employee.employee_id, lines).items():
                shown[(quarter, f"w2.{name}", employee.employee_id)] = amount
    return shown


def outcome(value: ExtractedValue | None, shown: Decimal) -> str:
    if value is None:
        return "missed"  # the document shows it, extraction never produced it
    if value.value is None:
        return "unreadable"  # not read, and sent to a person: safe
    if value.value == shown:
        return "correct"
    if value.confidence < REVIEW_THRESHOLD:
        return "wrong_but_flagged"  # wrong, but a person checks it: safe
    return "confidently_wrong"  # wrong AND trusted: the dangerous one


def grade(shown: dict[Key, Decimal], read: dict[Key, ExtractedValue]) -> dict:
    """Compare every value a document shows with what extraction produced."""
    documents: dict[str, Counter] = defaultdict(Counter)
    problems = []
    for key, amount in sorted(shown.items(), key=str):
        result = outcome(read.get(key), amount)
        documents[key[1].split(".")[0]][result] += 1  # "w2.box_1" -> "w2"
        if result != "correct":
            quarter, field, employee = key
            problems.append(f"{quarter} {field} {employee or ''}: {result}".strip())

    totals = sum(documents.values(), Counter())
    return {
        "documents": {name: dict(counts) for name, counts in sorted(documents.items())},
        "accuracy": totals["correct"] / len(shown),
        "confidently_wrong": totals["confidently_wrong"],
        # A value no document shows was made up: the worst failure of all
        "invented": sorted(str(key) for key in read.keys() - shown.keys()),
        "problems": problems,
    }


def run_extraction_eval() -> dict:
    read = {}
    with tempfile.TemporaryDirectory() as scratch:  # an eval must not touch saved data
        for quarter in QUARTERS:
            for value in run_extraction(quarter, extracted_dir=Path(scratch)).values:
                read[(quarter, value.field, value.employee_id)] = value
    return grade(printed_values(), read)
