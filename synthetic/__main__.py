"""Generate all synthetic source documents plus the golden answer key.

Run with: uv run python -m synthetic
"""

import json
from decimal import Decimal
from pathlib import Path

from synthetic.employees import SEED, generate_employees
from synthetic.form941 import TYPO_QUARTER, compute_941, write_941
from synthetic.payroll import (
    BONUS_EMPLOYEE_ID,
    BONUS_QUARTER,
    QUARTERS,
    PayrollLine,
    generate_payroll,
    money,
)
from synthetic.register import (
    MISSING_EMPLOYEE_ID,
    MISSING_QUARTER,
    OUTPUT_DIR,
    write_register,
)
from synthetic.w2 import BLURRY_EMPLOYEE_ID, TAX_YEAR, compute_w2, write_w2

# The answer key lives apart from the source files, so the system never sees it
GOLDEN_PATH = Path("data/golden/golden.json")


def gross(
    lines: list[PayrollLine], quarter: str, employee_id: str | None = None
) -> Decimal:
    return sum(
        line.gross_wages
        for line in lines
        if line.quarter == quarter
        and (employee_id is None or line.employee_id == employee_id)
    )


def build_golden(lines: list[PayrollLine]) -> dict:
    true_wages = gross(lines, TYPO_QUARTER)
    reported_wages = compute_941(TYPO_QUARTER, lines)["line_2"]

    previous = QUARTERS[QUARTERS.index(BONUS_QUARTER) - 1]
    before = gross(lines, previous, BONUS_EMPLOYEE_ID)
    after = gross(lines, BONUS_QUARTER, BONUS_EMPLOYEE_ID)

    # Decimals are written as strings: JSON numbers are floats and lose precision
    return {
        "seed": SEED,
        "quarters": QUARTERS,
        "planted_errors": [
            {
                "id": 1,
                "type": "reconciliation_mismatch",
                "check": "register_vs_941_wages",
                "quarter": TYPO_QUARTER,
                "cause": "Form 941 line 2 has two digits transposed",
                "true_value": str(true_wages),
                "reported_value": str(reported_wages),
                "difference": str(reported_wages - true_wages),
            },
            {
                "id": 2,
                "type": "missing_employee",
                "check": "register_vs_941_wages",
                "quarter": MISSING_QUARTER,
                "employee_id": MISSING_EMPLOYEE_ID,
                "cause": "Employee left out of the payroll register",
                "difference": str(gross(lines, MISSING_QUARTER, MISSING_EMPLOYEE_ID)),
            },
            {
                "id": 3,
                "type": "variance",
                "check": "quarter_over_quarter_wages",
                "employee_id": BONUS_EMPLOYEE_ID,
                "from_quarter": previous,
                "to_quarter": BONUS_QUARTER,
                "change_percent": str(money((after - before) / before * 100)),
                "cause": "One-off bonus (valid, but must be explained)",
            },
            {
                "id": 4,
                "type": "low_confidence_document",
                "document": f"w2_{TAX_YEAR}_{BLURRY_EMPLOYEE_ID}.pdf",
                "cause": "Low-quality scan with no text layer",
            },
        ],
    }


def main() -> None:
    employees = generate_employees()
    lines = generate_payroll(employees)

    for quarter in QUARTERS:
        write_register(quarter, employees, lines)
        write_941(quarter, compute_941(quarter, lines))
    for e in employees:
        write_w2(e, compute_w2(e.employee_id, lines))

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(build_golden(lines), indent=2))

    print(f"Source documents: {OUTPUT_DIR}")
    print(f"Answer key:       {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
