from decimal import Decimal

import pytest
from pydantic import ValidationError

from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "a" * 64


def test_pdf_value_with_page_and_box():
    ref = SourceRef(file_sha256=HASH, page=1, bbox=(460, 168, 520, 180))
    value = ExtractedValue(
        field="form_941.line_2", value=Decimal("519745.00"), confidence=0.99, source=ref
    )

    assert value.value == Decimal("519745.00")
    assert value.source.page == 1


def test_excel_value_with_sheet_and_cell():
    ref = SourceRef(file_sha256=HASH, sheet="Register", cell="F4")

    assert ref.cell == "F4"


def test_unreadable_value_is_none_with_zero_confidence():
    ref = SourceRef(file_sha256=HASH, page=1)
    value = ExtractedValue(field="w2.box_1", value=None, confidence=0.0, source=ref)

    assert value.value is None


@pytest.mark.parametrize("confidence", [-0.1, 1.7])
def test_confidence_must_be_between_0_and_1(confidence):
    with pytest.raises(ValidationError):
        ExtractedValue(
            field="x",
            value=Decimal(1),
            confidence=confidence,
            source=SourceRef(file_sha256=HASH, page=1),
        )


def test_source_must_point_somewhere():
    with pytest.raises(ValidationError):
        SourceRef(file_sha256=HASH)


def test_source_cannot_be_both_pdf_and_excel():
    with pytest.raises(ValidationError):
        SourceRef(file_sha256=HASH, page=1, cell="F4")


def test_hash_must_be_a_real_sha256():
    with pytest.raises(ValidationError):
        SourceRef(file_sha256="not-a-hash", page=1)


def test_values_cannot_be_edited_after_creation():
    ref = SourceRef(file_sha256=HASH, page=1)

    with pytest.raises(ValidationError):
        ref.page = 2
