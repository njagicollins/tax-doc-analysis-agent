from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from synthetic.employees import Employee, generate_employees

CENT = Decimal("0.01")
FEDERAL_RATE = Decimal("0.12")  # simplified flat rate
SS_RATE = Decimal("0.062")
SS_WAGE_BASE = Decimal(176100)
MEDICARE_RATE = Decimal("0.0145")

QUARTERS = ["2026Q1", "2026Q2"]

# Planted error #3: one employee gets a 40% bonus in Q2
BONUS_EMPLOYEE_ID = "E007"
BONUS_QUARTER = "2026Q2"
BONUS_RATE = Decimal("0.40")


def money(amount: Decimal) -> Decimal:
    """Round to cents, the way accountants do (0.005 rounds up)."""
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class PayrollLine:
    employee_id: str
    quarter: str
    regular_wages: Decimal
    bonus: Decimal
    gross_wages: Decimal
    ss_wages: Decimal
    federal_tax: Decimal
    ss_tax: Decimal
    medicare_tax: Decimal


def generate_payroll(
    employees: list[Employee], quarters: list[str] = QUARTERS
) -> list[PayrollLine]:
    lines = []
    ss_wages_so_far = {e.employee_id: Decimal(0) for e in employees}

    for quarter in quarters:
        for e in employees:
            regular = money(e.annual_salary / 4)

            gets_bonus = e.employee_id == BONUS_EMPLOYEE_ID and quarter == BONUS_QUARTER
            bonus = money(regular * BONUS_RATE) if gets_bonus else Decimal("0.00")
            gross = regular + bonus

            # Social Security stops once the yearly wage base is reached
            room_left = max(SS_WAGE_BASE - ss_wages_so_far[e.employee_id], Decimal(0))
            ss_wages = min(gross, room_left)
            ss_wages_so_far[e.employee_id] += ss_wages

            lines.append(
                PayrollLine(
                    employee_id=e.employee_id,
                    quarter=quarter,
                    regular_wages=regular,
                    bonus=bonus,
                    gross_wages=gross,
                    ss_wages=ss_wages,
                    federal_tax=money(gross * FEDERAL_RATE),
                    ss_tax=money(ss_wages * SS_RATE),
                    medicare_tax=money(gross * MEDICARE_RATE),
                )
            )
    return lines


if __name__ == "__main__":
    for line in generate_payroll(generate_employees()):
        if line.employee_id in ("E001", "E007"):
            print(line)
