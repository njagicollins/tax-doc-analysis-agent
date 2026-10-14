import pytest

from evals.detection import Signal, expected, run_detection, score
from tests.test_workflow import world  # noqa: F401  (a generated, ingested world)

QUARTERS = ["2026Q1", "2026Q2"]
TYPO = {
    "id": 1,
    "type": "reconciliation_mismatch",
    "check": "register_vs_941_wages",
    "quarter": "2026Q2",
    "cause": "two digits swapped",
}
LEFT_OUT = {
    "id": 2,
    "type": "missing_employee",
    "quarter": "2026Q1",
    "employee_id": "E013",
    "cause": "left out of the register",
}

TYPO_RAISED = Signal("2026Q2", "reconciliation", "register_vs_941_wages")
LEFT_OUT_RAISED = Signal(
    "2026Q1", "missing_employee", "payroll_db_vs_register_employees", "E013"
)


def test_every_error_found_and_nothing_else_is_a_perfect_score():
    result = score([TYPO, LEFT_OUT], {TYPO_RAISED, LEFT_OUT_RAISED}, QUARTERS)

    assert [error["found"] for error in result["errors"]] == [True, True]
    assert (result["recall"], result["precision"]) == (1.0, 1.0)
    assert result["unexpected"] == []


def test_a_missed_error_lowers_recall_and_says_what_was_missing():
    result = score([TYPO, LEFT_OUT], {TYPO_RAISED}, QUARTERS)

    missed = result["errors"][1]
    assert not missed["found"]
    assert missed["missing"][0]["employee_id"] == "E013"
    assert result["recall"] == 0.5


def test_a_false_alarm_lowers_precision_and_is_listed():
    false_alarm = Signal(
        "2026Q2", "variance", "quarter_over_quarter_gross_wages", "E001"
    )

    result = score([TYPO], {TYPO_RAISED, false_alarm}, QUARTERS)

    assert result["recall"] == 1.0  # the real error was still found
    assert result["precision"] == 0.5
    assert result["unexpected"][0]["employee_id"] == "E001"


def test_side_effects_of_a_planted_error_are_not_false_alarms():
    totals_off = Signal("2026Q1", "reconciliation", "register_vs_payroll_db_wages")

    result = score([LEFT_OUT], {LEFT_OUT_RAISED, totals_off}, QUARTERS)

    assert result["unexpected"] == []
    assert result["precision"] == 1.0


def test_a_side_effect_alone_does_not_count_as_finding_the_error():
    totals_off = Signal("2026Q1", "reconciliation", "register_vs_payroll_db_wages")

    result = score([LEFT_OUT], {totals_off}, QUARTERS)

    assert not result["errors"][0]["found"]  # we saw smoke, but not the fire


def test_an_unreadable_document_must_be_sent_to_review_in_every_quarter():
    blurry = {"type": "low_confidence_document", "document": "w2_2026_E017.pdf"}

    must, may = expected(blurry, QUARTERS)

    assert must == {Signal(q, "needs_review", "w2", "E017") for q in QUARTERS}
    assert may == set()


def test_a_new_kind_of_planted_error_needs_a_rule():
    with pytest.raises(ValueError, match="ghost_employee"):
        expected({"type": "ghost_employee"}, QUARTERS)


def test_the_real_pipeline_finds_all_four_planted_errors(world):  # noqa: F811
    result = run_detection()

    assert [error["found"] for error in result["errors"]] == [True] * 4
    assert result["unexpected"] == []
    assert (result["recall"], result["precision"]) == (1.0, 1.0)
