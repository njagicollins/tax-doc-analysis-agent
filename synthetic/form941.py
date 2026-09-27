from decimal import Decimal
from pathlib import Path

import pymupdf

from synthetic.employees import generate_employees
from synthetic.payroll import QUARTERS, PayrollLine, generate_payroll, money
from synthetic.register import OUTPUT_DIR

SS_COMBINED_RATE = Decimal("0.124")  # employee 6.2% + employer 6.2%
MEDICARE_COMBINED_RATE = Decimal("0.029")  # employee 1.45% + employer 1.45%
EMPLOYER = "Demo Payroll Co.  |  EIN: 00-0000000"

# Planted error #1: in Q2, line 2 (wages) is typed with two digits swapped
TYPO_QUARTER = "2026Q2"


def transpose_digits(amount: Decimal, position: int = 3) -> Decimal:
    """Swap two neighbouring digits: a classic data-entry typo."""
    chars = list(f"{amount:.2f}")
    chars[position], chars[position + 1] = chars[position + 1], chars[position]
    typo = Decimal("".join(chars))
    assert typo != amount, "digits were equal; choose another position"
    return typo


def compute_941(quarter: str, lines: list[PayrollLine]) -> dict[str, Decimal]:
    q = [line for line in lines if line.quarter == quarter]
    ss_wages = sum(line.ss_wages for line in q)
    medicare_wages = sum(line.gross_wages for line in q)

    figures = {
        "line_1": Decimal(len(q)),
        "line_2": sum(line.gross_wages for line in q),
        "line_3": sum(line.federal_tax for line in q),
        "line_5a_wages": ss_wages,
        "line_5a_tax": money(ss_wages * SS_COMBINED_RATE),
        "line_5c_wages": medicare_wages,
        "line_5c_tax": money(medicare_wages * MEDICARE_COMBINED_RATE),
    }
    figures["line_5e"] = figures["line_5a_tax"] + figures["line_5c_tax"]
    figures["line_6"] = figures["line_3"] + figures["line_5e"]

    if quarter == TYPO_QUARTER:
        figures["line_2"] = transpose_digits(figures["line_2"])
    return figures


def write_941(
    quarter: str, f: dict[str, Decimal], output_dir: Path = OUTPUT_DIR
) -> Path:
    rows = [
        ("1", "Number of employees who received wages", None, f"{f['line_1']:.0f}"),
        ("2", "Wages, tips, and other compensation", None, f"{f['line_2']:,.2f}"),
        ("3", "Federal income tax withheld", None, f"{f['line_3']:,.2f}"),
        (
            "5a",
            "Taxable social security wages",
            f"{f['line_5a_wages']:,.2f}",
            f"{f['line_5a_tax']:,.2f}",
        ),
        (
            "5c",
            "Taxable Medicare wages",
            f"{f['line_5c_wages']:,.2f}",
            f"{f['line_5c_tax']:,.2f}",
        ),
        (
            "5e",
            "Total social security and Medicare taxes",
            None,
            f"{f['line_5e']:,.2f}",
        ),
        ("6", "Total taxes before adjustments", None, f"{f['line_6']:,.2f}"),
    ]

    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)  # US Letter, in points (1/72 inch)
    page.insert_text(
        (72, 72), "Form 941  Employer's QUARTERLY Federal Tax Return", fontsize=14
    )
    page.insert_text((72, 94), f"Quarter: {quarter}    {EMPLOYER}", fontsize=10)

    y = 140
    for number, label, column_1, column_2 in rows:
        page.insert_text((72, y), number, fontsize=11)
        page.insert_text((100, y), label, fontsize=11)
        if column_1:
            page.insert_text((350, y), column_1, fontsize=11)
        page.insert_text((460, y), column_2, fontsize=11)
        y += 28

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"form_941_{quarter}.pdf"
    doc.save(path)
    return path


if __name__ == "__main__":
    lines = generate_payroll(generate_employees())
    for quarter in QUARTERS:
        figures = compute_941(quarter, lines)
        print(write_941(quarter, figures), "line 2 =", f"{figures['line_2']:,.2f}")
