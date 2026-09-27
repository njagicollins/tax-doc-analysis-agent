from decimal import Decimal

from synthetic.__main__ import build_golden
from synthetic.employees import generate_employees
from synthetic.payroll import generate_payroll


def test_same_seed_gives_same_employees():
    assert generate_employees() == generate_employees()


def test_golden_answers():
    golden = build_golden(generate_payroll(generate_employees()))
    errors = {error["id"]: error for error in golden["planted_errors"]}

    assert errors[1]["difference"] == "270.00"
    assert errors[2]["difference"] == "37500.00"
    assert errors[3]["change_percent"] == "40.00"
    assert errors[4]["document"] == "w2_2026_E017.pdf"


def test_transposition_difference_is_divisible_by_9():
    golden = build_golden(generate_payroll(generate_employees()))
    typo = golden["planted_errors"][0]

    assert Decimal(typo["difference"]) % 9 == 0
