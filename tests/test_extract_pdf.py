from decimal import Decimal

import pytest

from synthetic.employees import generate_employees
from synthetic.form941 import compute_941, write_941
from synthetic.payroll import generate_payroll
from synthetic.w2 import compute_w2, write_w2
from taxagent.extraction.pdf import extract_941, extract_w2

HASH = "c" * 64


@pytest.fixture(scope="module")
def world():
    employees = generate_employees()
    return {e.employee_id: e for e in employees}, generate_payroll(employees)


def by_field(values):
    return {v.field: v for v in values}


def test_941_is_read_exactly_as_printed_typo_included(world, tmp_path):
    _, lines = world
    path = write_941("2026Q2", compute_941("2026Q2", lines), tmp_path)

    values = by_field(extract_941(path, HASH))

    assert values["form_941.line_2"].value == Decimal("519745.00")  # the planted typo
    assert values["form_941.line_5a_wages"].value == Decimal("519475.00")
    assert values["form_941.line_1"].value == 20
    assert len(values) == 9


def test_941_values_point_to_their_box_on_the_page(world, tmp_path):
    _, lines = world
    path = write_941("2026Q2", compute_941("2026Q2", lines), tmp_path)

    line_2 = by_field(extract_941(path, HASH))["form_941.line_2"]

    assert line_2.source.page == 1
    left_edge = line_2.source.bbox[0]
    assert left_edge >= 400  # right of the label, in the amount column
    assert line_2.confidence == 0.98


def test_w2_values_and_employee_id(world, tmp_path):
    employees, lines = world
    e007 = employees["E007"]
    path = write_w2(e007, compute_w2("E007", lines), tmp_path)

    values = extract_w2(path, HASH)

    assert {v.employee_id for v in values} == {"E007"}
    assert by_field(values)["w2.box_1"].value == Decimal("68100.00")  # Q1 + Q2 + bonus


def test_id_printed_on_the_form_beats_the_file_name_hint(world, tmp_path):
    employees, lines = world
    path = write_w2(employees["E007"], compute_w2("E007", lines), tmp_path)

    values = extract_w2(path, HASH, employee_id_hint="E999")

    assert {v.employee_id for v in values} == {"E007"}


def test_scanned_w2_is_unreadable_never_guessed(world, tmp_path):
    employees, lines = world
    path = write_w2(employees["E017"], compute_w2("E017", lines), tmp_path)

    values = extract_w2(path, HASH, employee_id_hint="E017")

    assert len(values) == 6
    assert all(v.value is None and v.confidence == 0.0 for v in values)
    assert {v.employee_id for v in values} == {"E017"}
