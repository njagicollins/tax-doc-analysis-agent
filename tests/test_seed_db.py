import sqlite3

from mock_sources.seed_db import seed_database
from synthetic.employees import generate_employees
from synthetic.payroll import generate_payroll


def query(db_path, sql):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def seeded(tmp_path):
    employees = generate_employees()
    return seed_database(employees, generate_payroll(employees), tmp_path / "t.db")


def test_all_employees_and_payroll_rows_are_stored(tmp_path):
    db = seeded(tmp_path)
    assert query(db, "SELECT COUNT(*) FROM employees") == [(20,)]
    assert query(db, "SELECT COUNT(*) FROM payroll") == [(40,)]


def test_database_is_complete_unlike_the_register(tmp_path):
    db = seeded(tmp_path)
    rows = query(
        db,
        "SELECT gross_wages_cents FROM payroll WHERE employee_id = 'E013' AND quarter = '2026Q1'",
    )
    assert rows == [(3_750_000,)]


def test_quarter_totals_in_cents(tmp_path):
    db = seeded(tmp_path)
    rows = query(
        db,
        "SELECT quarter, SUM(gross_wages_cents) FROM payroll GROUP BY quarter ORDER BY quarter",
    )
    assert rows == [("2026Q1", 50_812_500), ("2026Q2", 51_947_500)]
