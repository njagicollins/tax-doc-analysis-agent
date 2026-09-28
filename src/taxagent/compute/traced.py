"""Traced amounts: numbers that carry the evidence they were built from.

Every function here is pure: no files, no network, no clock, no randomness.
"""

from dataclasses import dataclass
from decimal import Decimal

from taxagent.schema.models import ExtractedValue, SourceRef


class UnreadableValueError(Exception):
    """Math was asked to use a value nobody could read. A human must fill it first."""


@dataclass(frozen=True)
class Traced:
    value: Decimal
    sources: tuple[SourceRef, ...]


def traced(extracted: ExtractedValue) -> Traced:
    if extracted.value is None:
        who = f" for {extracted.employee_id}" if extracted.employee_id else ""
        raise UnreadableValueError(f"{extracted.field}{who} could not be read")
    return Traced(extracted.value, (extracted.source,))


def total(values: list[ExtractedValue]) -> Traced:
    """Add up values, keeping every one of their sources."""
    parts = [traced(v) for v in values]
    return Traced(
        value=sum((p.value for p in parts), Decimal(0)),
        sources=tuple(source for p in parts for source in p.sources),
    )
