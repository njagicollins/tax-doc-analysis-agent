from decimal import Decimal

import pytest

from taxagent.review.corrections import amount_problem, apply_corrections
from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "3" * 64


def unreadable(field, employee_id="E017"):
    return ExtractedValue(
        field=field,
        employee_id=employee_id,
        value=None,
        confidence=0.0,
        source=SourceRef(file_sha256=HASH, page=1),
    )


def correction(field, value, employee_id="E017", by="alice"):
    return {"field": field, "employee_id": employee_id, "value": value, "by": by}


def test_correction_replaces_the_value_and_records_who():
    [fixed] = apply_corrections(
        [unreadable("w2.box_1")], [correction("w2.box_1", "75000.00")]
    )

    assert fixed.value == Decimal("75000.00")
    assert (fixed.confidence, fixed.corrected_by) == (1.0, "alice")


def test_corrected_value_still_points_to_its_document():
    original = unreadable("w2.box_1")

    [fixed] = apply_corrections([original], [correction("w2.box_1", "1.00")])

    assert fixed.source == original.source


def test_values_without_corrections_are_untouched():
    other = unreadable("w2.box_2")

    result = apply_corrections(
        [unreadable("w2.box_1"), other], [correction("w2.box_1", "1.00")]
    )

    assert result[1] is other


def test_a_correction_that_matches_nothing_fails_loudly():
    with pytest.raises(ValueError, match="w2.box_9"):
        apply_corrections([unreadable("w2.box_1")], [correction("w2.box_9", "1.00")])


@pytest.mark.parametrize(
    ("raw", "problem"),
    [
        ("75000.00", None),
        ("0", None),
        ("abc", "is not a number"),
        (None, "is not a number"),
        ("NaN", "must be a real number"),
        ("Infinity", "must be a real number"),
        ("-500", "cannot be negative"),
    ],
)
def test_amount_problem(raw, problem):
    assert amount_problem(raw) == problem
