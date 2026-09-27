from decimal import Decimal

from mock_sources.seed_db import seed_database
from synthetic.employees import generate_employees
from synthetic.payroll import generate_payroll
from taxagent.extraction.csv_snapshot import extract_payroll_snapshot
from taxagent.ingestion.sources import SqlPayrollSource

HASH = "d" * 64


def snapshot(tmp_path, quarter):
    employees = generate_employees()
    db = seed_database(employees, generate_payroll(employees), tmp_path / "p.db")
    [(name, content)] = SqlPayrollSource(db).fetch_documents(quarter)
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_cents_become_exact_dollars(tmp_path):
    values = extract_payroll_snapshot(snapshot(tmp_path, "2026Q1"), HASH)
    [gross] = [
        v
        for v in values
        if v.field == "payroll_db.gross_wages" and v.employee_id == "E013"
    ]

    assert gross.value == Decimal("37500.00")  # the employee the register left out
    assert gross.confidence == 1.0


def test_every_value_points_to_a_cell(tmp_path):
    values = extract_payroll_snapshot(snapshot(tmp_path, "2026Q1"), HASH)
    [first] = [
        v
        for v in values
        if v.field == "payroll_db.gross_wages" and v.employee_id == "E001"
    ]

    assert first.source.cell == "G2"  # column 7 (gross_wages_cents), row 2
    assert len(values) == 20 * 6
