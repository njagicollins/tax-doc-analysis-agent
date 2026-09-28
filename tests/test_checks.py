from decimal import Decimal

import pytest

from taxagent.compute.checks import reconcile, variance
from taxagent.compute.traced import Traced
from taxagent.schema.models import SourceRef

HASH = "f" * 64


def amount(value, cell="A1"):
    return Traced(Decimal(value), (SourceRef(file_sha256=HASH, cell=cell),))


def test_matching_documents_reconcile():
    result = reconcile("wages", amount("519475.00"), amount("519475.00"))

    assert result.matches
    assert result.difference == 0


def test_the_planted_typo_is_a_mismatch():
    result = reconcile("wages", amount("519475.00"), amount("519745.00"))

    assert not result.matches
    assert result.difference == Decimal("270.00")


@pytest.mark.parametrize(
    ("difference", "matches"),
    [("0.99", True), ("1.00", True), ("1.01", False), ("-1.01", False)],
)
def test_tolerance_boundary(difference, matches):
    result = reconcile(
        "tax", amount("1000.00"), amount(Decimal("1000.00") + Decimal(difference))
    )

    assert result.matches is matches


def test_reconciliation_keeps_both_sides_evidence():
    result = reconcile("wages", amount("1", "F4"), amount("1", "G2"))

    assert [s.cell for s in result.left.sources + result.right.sources] == ["F4", "G2"]


def test_the_planted_bonus_is_a_flagged_variance():
    result = variance("E007 wages", amount("28375.00"), amount("39725.00"))

    assert result.change == Decimal("11350.00")
    assert result.change_pct == Decimal("40.00")
    assert result.flagged


def test_small_changes_are_not_flagged():
    result = variance("E001 wages", amount("31625.00"), amount("31625.00"))

    assert result.change_pct == 0
    assert not result.flagged


def test_drops_are_flagged_too():
    assert variance("x", amount("100"), amount("50")).flagged


def test_change_from_zero_has_no_percentage_but_is_flagged():
    result = variance("new hire", amount("0"), amount("37500.00"))

    assert result.change_pct is None
    assert result.flagged
