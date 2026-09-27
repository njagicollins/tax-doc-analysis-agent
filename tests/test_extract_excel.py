from decimal import Decimal

import pytest
from openpyxl import load_workbook

from synthetic.employees import generate_employees
from synthetic.payroll import generate_payroll
from synthetic.register import write_register
from taxagent.extraction.excel import extract_register, to_money
from taxagent.ingestion.raw_store import sha256_of

HASH = "b" * 64


@pytest.fixture
def q1_register(tmp_path):
    employees = generate_employees()
    return write_register("2026Q1", employees, generate_payroll(employees), tmp_path)


def find(values, field, employee_id):
    [match] = [v for v in values if v.field == field and v.employee_id == employee_id]
    return match


def test_reads_value_and_exact_cell(q1_register):
    values = extract_register(q1_register, HASH)
    gross = find(values, "register.gross_wages", "E001")

    assert gross.value == Decimal("31625.00")
    assert gross.confidence == 1.0
    assert (gross.source.sheet, gross.source.cell) == ("Register", "F4")


def test_every_employee_row_except_the_missing_one(q1_register):
    values = extract_register(q1_register, HASH)
    employees = {v.employee_id for v in values}

    assert len(employees) == 19
    assert "E013" not in employees
    assert len(values) == 19 * 6  # six money columns per employee


def test_cents_survive_the_trip_through_excel(q1_register):
    medicare = find(
        extract_register(q1_register, HASH), "register.medicare_tax", "E001"
    )

    assert medicare.value == Decimal("458.56")


def test_source_hash_is_the_real_file_hash(q1_register):
    digest = sha256_of(q1_register.read_bytes())
    values = extract_register(q1_register, digest)

    assert all(v.source.file_sha256 == digest for v in values)


def test_header_is_found_wherever_it_is(q1_register):
    workbook = load_workbook(q1_register)
    workbook.active.insert_rows(1, amount=2)  # push everything down two rows
    workbook.save(q1_register)

    gross = find(extract_register(q1_register, HASH), "register.gross_wages", "E001")

    assert gross.source.cell == "F6"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (31625, (Decimal("31625.00"), 1.0)),
        (458.56, (Decimal("458.56"), 1.0)),
        ("31,625.00", (Decimal("31625.00"), 0.9)),
        ("n/a", (None, 0.0)),
        (None, (None, 0.0)),
    ],
)
def test_to_money(raw, expected):
    assert to_money(raw) == expected
