"""Run every check over a quarter's extracted values and collect the findings.

A finding is what analysts call an "exception": something a human must look at.
(We avoid that word in code because Python's Exception means an error.)
"""

from dataclasses import dataclass
from decimal import Decimal

from taxagent.compute.checks import reconcile, variance
from taxagent.compute.traced import total, traced
from taxagent.schema.models import ExtractedValue, SourceRef


@dataclass(frozen=True)
class Finding:
    kind: str  # "reconciliation", "missing_employee", "extra_employee", "variance"
    check: str
    quarter: str
    summary: str
    employee_id: str | None = None
    difference: Decimal | None = None
    change_pct: Decimal | None = None
    sources: tuple[SourceRef, ...] = ()


def select(values: list[ExtractedValue], field: str) -> list[ExtractedValue]:
    return [v for v in values if v.field == field]


def by_employee(values: list[ExtractedValue], field: str) -> dict[str, ExtractedValue]:
    return {v.employee_id: v for v in select(values, field)}


def reconciliation_findings(
    quarter: str, values: list[ExtractedValue]
) -> list[Finding]:
    register = total(select(values, "register.gross_wages"))
    [line_2] = select(values, "form_941.line_2")
    others = {
        "Form 941 line 2": ("register_vs_941_wages", traced(line_2)),
        "payroll database": (
            "register_vs_payroll_db_wages",
            total(select(values, "payroll_db.gross_wages")),
        ),
    }

    findings = []
    for label, (check, other) in others.items():
        result = reconcile(check, register, other)
        if not result.matches:
            findings.append(
                Finding(
                    kind="reconciliation",
                    check=check,
                    quarter=quarter,
                    difference=result.difference,
                    sources=register.sources + other.sources,
                    summary=(
                        f"Register gross wages {register.value:,.2f} vs {label} "
                        f"{other.value:,.2f}: difference {result.difference:,.2f}"
                    ),
                )
            )
    return findings


def employee_list_findings(quarter: str, values: list[ExtractedValue]) -> list[Finding]:
    register = by_employee(values, "register.gross_wages")
    payroll_db = by_employee(values, "payroll_db.gross_wages")

    missing = [
        Finding(
            kind="missing_employee",
            check="payroll_db_vs_register_employees",
            quarter=quarter,
            employee_id=employee_id,
            difference=payroll_db[employee_id].value,
            sources=(payroll_db[employee_id].source,),
            summary=(
                f"{employee_id} is in the payroll database "
                f"({payroll_db[employee_id].value:,.2f}) but not in the register"
            ),
        )
        for employee_id in sorted(payroll_db.keys() - register.keys())
    ]
    # The reverse is worse: someone is paid in the register but does not exist
    extra = [
        Finding(
            kind="extra_employee",
            check="payroll_db_vs_register_employees",
            quarter=quarter,
            employee_id=employee_id,
            difference=register[employee_id].value,
            sources=(register[employee_id].source,),
            summary=(
                f"{employee_id} is paid in the register "
                f"({register[employee_id].value:,.2f}) but is not in the payroll "
                "database (possible ghost employee)"
            ),
        )
        for employee_id in sorted(register.keys() - payroll_db.keys())
    ]
    return missing + extra


def variance_findings(
    quarter: str, current: list[ExtractedValue], previous: list[ExtractedValue]
) -> list[Finding]:
    now = by_employee(current, "register.gross_wages")
    before = by_employee(previous, "register.gross_wages")

    findings = []
    # Only employees in both quarters: missing ones are the employee-list check's job
    for employee_id in sorted(now.keys() & before.keys()):
        result = variance(
            f"{employee_id} gross wages",
            traced(before[employee_id]),
            traced(now[employee_id]),
        )
        if result.flagged:
            findings.append(
                Finding(
                    kind="variance",
                    check="quarter_over_quarter_gross_wages",
                    quarter=quarter,
                    employee_id=employee_id,
                    difference=result.change,
                    change_pct=result.change_pct,
                    sources=result.previous.sources + result.current.sources,
                    summary=(
                        f"{employee_id} gross wages {result.previous.value:,.2f} -> "
                        f"{result.current.value:,.2f} ({result.change_pct:+}%)"
                    ),
                )
            )
    return findings


def run_checks(
    quarter: str,
    current: list[ExtractedValue],
    previous: list[ExtractedValue] | None = None,
) -> list[Finding]:
    findings = reconciliation_findings(quarter, current)
    findings += employee_list_findings(quarter, current)
    if previous is not None:
        findings += variance_findings(quarter, current, previous)
    return findings
