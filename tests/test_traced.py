from decimal import Decimal

import pytest

from taxagent.compute.traced import UnreadableValueError, total, traced
from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "e" * 64


def value(amount, cell="A1", employee_id="E001"):
    return ExtractedValue(
        field="register.gross_wages",
        employee_id=employee_id,
        value=None if amount is None else Decimal(amount),
        confidence=1.0 if amount is not None else 0.0,
        source=SourceRef(file_sha256=HASH, cell=cell),
    )


def test_total_adds_values_and_keeps_every_source():
    result = total([value("100.10", "F4"), value("200.20", "F5")])

    assert result.value == Decimal("300.30")
    assert [s.cell for s in result.sources] == ["F4", "F5"]


def test_total_of_nothing_is_zero_with_no_sources():
    result = total([])

    assert result.value == Decimal(0)
    assert result.sources == ()


def test_math_refuses_unreadable_values():
    with pytest.raises(UnreadableValueError, match="E017"):
        total([value("100"), value(None, employee_id="E017")])


def test_single_value_keeps_its_source():
    result = traced(value("5.00", "G2"))

    assert (result.value, result.sources[0].cell) == (Decimal("5.00"), "G2")
