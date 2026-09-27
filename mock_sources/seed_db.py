"""Seed the mock payroll SQL database (stands in for the company's SaaS SQL DB).

Run with: uv run python -m mock_sources.seed_db
"""

import sqlite3
from decimal import Decimal
from pathlib import Path

from synthetic.employees import Employee, generate_employees
from synthetic.payroll import PayrollLine, generate_payroll

DB_PATH = Path("data/sources/sql/payroll.db")

SCHEMA = """
CREATE TABLE employees (
    employee_id          TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    ssn                  TEXT NOT NULL,
    annual_salary_cents  INTEGER NOT NULL
);

CREATE TABLE payroll (
    employee_id          TEXT NOT NULL REFERENCES employees (employee_id),
    quarter              TEXT NOT NULL,
    regular_wages_cents  INTEGER NOT NULL,
    bonus_cents          INTEGER NOT NULL,
    gross_wages_cents    INTEGER NOT NULL,
    federal_tax_cents    INTEGER NOT NULL,
    ss_wages_cents       INTEGER NOT NULL,
    ss_tax_cents         INTEGER NOT NULL,
    medicare_tax_cents   INTEGER NOT NULL,
    PRIMARY KEY (employee_id, quarter)
);
"""


def to_cents(amount: Decimal) -> int:
    """Store money as whole cents: databases have no exact decimal type here."""
    cents = amount * 100
    assert cents == cents.to_integral_value(), f"{amount} has fractions of a cent"
    return int(cents)


def seed_database(
    employees: list[Employee], lines: list[PayrollLine], db_path: Path = DB_PATH
) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)  # always rebuild from scratch

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO employees VALUES (?, ?, ?, ?)",
            [
                (e.employee_id, e.name, e.ssn, to_cents(e.annual_salary))
                for e in employees
            ],
        )
        conn.executemany(
            "INSERT INTO payroll VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    line.employee_id,
                    line.quarter,
                    to_cents(line.regular_wages),
                    to_cents(line.bonus),
                    to_cents(line.gross_wages),
                    to_cents(line.federal_tax),
                    to_cents(line.ss_wages),
                    to_cents(line.ss_tax),
                    to_cents(line.medicare_tax),
                )
                for line in lines
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


if __name__ == "__main__":
    employees = generate_employees()
    print(seed_database(employees, generate_payroll(employees)))
