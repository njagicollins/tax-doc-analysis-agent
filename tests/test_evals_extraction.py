from decimal import Decimal

from evals.extraction import grade, outcome, printed_values, run_extraction_eval
from taxagent.schema.models import ExtractedValue, SourceRef
from tests.test_workflow import world  # noqa: F401  (a generated, ingested world)


def read_as(value, confidence=1.0):
    source = SourceRef(file_sha256="0" * 64, page=1)
    return ExtractedValue(
        field="w2.box_1", value=value, confidence=confidence, source=source
    )


SHOWN = Decimal("63250.00")


def test_each_kind_of_outcome():
    assert outcome(read_as(Decimal("63250.00")), SHOWN) == "correct"
    assert outcome(read_as(None, confidence=0.3), SHOWN) == "unreadable"
    assert outcome(read_as(Decimal("63520.00"), 0.6), SHOWN) == "wrong_but_flagged"
    assert outcome(read_as(Decimal("63520.00")), SHOWN) == "confidently_wrong"
    assert outcome(None, SHOWN) == "missed"


def test_the_same_amount_written_differently_is_still_correct():
    assert outcome(read_as(Decimal(63250)), SHOWN) == "correct"


def test_grade_counts_per_document_and_lists_every_problem():
    key_ok = ("2026Q2", "w2.box_1", "E001")
    key_bad = ("2026Q2", "w2.box_1", "E002")
    shown = {key_ok: SHOWN, key_bad: SHOWN}
    read = {key_ok: read_as(SHOWN), key_bad: read_as(Decimal("1.00"))}

    result = grade(shown, read)

    assert result["documents"] == {"w2": {"correct": 1, "confidently_wrong": 1}}
    assert result["accuracy"] == 0.5
    assert result["confidently_wrong"] == 1
    assert result["problems"] == ["2026Q2 w2.box_1 E002: confidently_wrong"]


def test_a_value_no_document_shows_is_reported_as_invented():
    key = ("2026Q2", "w2.box_1", "E001")
    ghost = ("2026Q2", "w2.box_1", "E999")

    result = grade({key: SHOWN}, {key: read_as(SHOWN), ghost: read_as(SHOWN)})

    assert result["invented"] == [str(ghost)]


def test_the_941_typo_is_what_the_form_shows():
    shown = printed_values()

    # Reading the transposed number is correct extraction; the checks catch it
    assert shown[("2026Q2", "form_941.line_2", None)] == Decimal("519745.00")


def test_the_register_does_not_show_the_left_out_employee():
    shown = printed_values()

    assert ("2026Q1", "register.gross_wages", "E013") not in shown
    assert ("2026Q1", "payroll_db.gross_wages", "E013") in shown


def test_the_real_extraction_is_never_confidently_wrong(world):  # noqa: F811
    result = run_extraction_eval()

    assert result["confidently_wrong"] == 0
    assert result["invented"] == []
    assert result["documents"]["w2"]["unreadable"] == 12  # E017, six boxes, twice
    assert len(result["problems"]) == 12  # nothing else went wrong
