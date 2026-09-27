from decimal import Decimal
from pathlib import Path

import pymupdf

from synthetic.employees import Employee, generate_employees
from synthetic.payroll import PayrollLine, generate_payroll
from synthetic.register import OUTPUT_DIR

TAX_YEAR = "2026"
EMPLOYER = "Demo Payroll Co.  |  EIN: 00-0000000"

# Simplification: W-2s cover Q1 + Q2 only (real W-2s cover the full year)

# Planted error #4: one W-2 arrives as a low-quality scan (no text layer)
BLURRY_EMPLOYEE_ID = "E017"
BLURRY_DPI = 40


def compute_w2(employee_id: str, lines: list[PayrollLine]) -> dict[str, Decimal]:
    mine = [line for line in lines if line.employee_id == employee_id]
    return {
        "box_1": sum(line.gross_wages for line in mine),
        "box_2": sum(line.federal_tax for line in mine),
        "box_3": sum(line.ss_wages for line in mine),
        "box_4": sum(line.ss_tax for line in mine),
        "box_5": sum(line.gross_wages for line in mine),
        "box_6": sum(line.medicare_tax for line in mine),
    }


def draw_w2(page: pymupdf.Page, e: Employee, boxes: dict[str, Decimal]) -> None:
    labels = [
        ("box_1", "1  Wages, tips, other compensation"),
        ("box_2", "2  Federal income tax withheld"),
        ("box_3", "3  Social security wages"),
        ("box_4", "4  Social security tax withheld"),
        ("box_5", "5  Medicare wages and tips"),
        ("box_6", "6  Medicare tax withheld"),
    ]
    page.insert_text(
        (72, 72), f"Form W-2  Wage and Tax Statement  {TAX_YEAR}", fontsize=14
    )
    page.insert_text((72, 94), EMPLOYER, fontsize=10)
    page.insert_text(
        (72, 124), f"Employee: {e.name}   ID: {e.employee_id}", fontsize=11
    )
    page.insert_text((72, 142), f"SSN: {e.ssn}", fontsize=11)

    y = 180
    for key, label in labels:
        page.insert_text((72, y), label, fontsize=11)
        page.insert_text((400, y), f"{boxes[key]:,.2f}", fontsize=11)
        y += 28


def make_blurry(doc: pymupdf.Document) -> pymupdf.Document:
    """Turn a clean PDF into a low-resolution scanned image with no text layer."""
    pix = doc[0].get_pixmap(dpi=BLURRY_DPI)
    scanned = pymupdf.open()
    page = scanned.new_page(width=612, height=792)
    page.insert_image(page.rect, pixmap=pix)
    return scanned


def write_w2(
    e: Employee, boxes: dict[str, Decimal], output_dir: Path = OUTPUT_DIR
) -> Path:
    doc = pymupdf.open()
    draw_w2(doc.new_page(width=612, height=792), e, boxes)

    if e.employee_id == BLURRY_EMPLOYEE_ID:
        doc = make_blurry(doc)

    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"w2_{TAX_YEAR}_{e.employee_id}.pdf"
    doc.save(path)
    return path


if __name__ == "__main__":
    employees = generate_employees()
    lines = generate_payroll(employees)
    for e in employees:
        write_w2(e, compute_w2(e.employee_id, lines))
    print(f"Wrote {len(employees)} W-2s to {OUTPUT_DIR}")
