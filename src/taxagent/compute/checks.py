"""Reconciliation and variance: the judge. Pure functions over traced amounts."""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from taxagent.compute.traced import Traced

TOLERANCE = Decimal("1.00")  # absorbs cent rounding; far below any real error
VARIANCE_THRESHOLD_PCT = Decimal(25)


@dataclass(frozen=True)
class Reconciliation:
    check: str
    left: Traced
    right: Traced
    difference: Decimal  # right minus left
    matches: bool


@dataclass(frozen=True)
class Variance:
    check: str
    previous: Traced
    current: Traced
    change: Decimal
    change_pct: Decimal | None  # None when there is no previous amount to compare
    flagged: bool


def reconcile(
    check: str, left: Traced, right: Traced, tolerance: Decimal = TOLERANCE
) -> Reconciliation:
    difference = right.value - left.value
    return Reconciliation(check, left, right, difference, abs(difference) <= tolerance)


def variance(
    check: str,
    previous: Traced,
    current: Traced,
    threshold_pct: Decimal = VARIANCE_THRESHOLD_PCT,
) -> Variance:
    change = current.value - previous.value
    if previous.value == 0:
        # A percentage of zero is undefined: flag any change for a human to judge
        return Variance(check, previous, current, change, None, change != 0)
    change_pct = (change / previous.value * 100).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return Variance(
        check, previous, current, change, change_pct, abs(change_pct) > threshold_pct
    )
