"""Human corrections: check them, then apply them to the extracted values.

A corrected value keeps its SourceRef (it still came from that document) and
records who typed it in, so the audit trail tells the truth about every number.
"""

from decimal import Decimal, InvalidOperation

from taxagent.schema.models import ExtractedValue


def amount_problem(raw: object) -> str | None:
    """Why this is not a usable money amount, or None if it is."""
    try:
        amount = Decimal(str(raw))
    except InvalidOperation:
        return "is not a number"
    if not amount.is_finite():  # Decimal happily accepts "NaN" and "Infinity"
        return "must be a real number"
    if amount < 0:
        return "cannot be negative"
    return None


def apply_corrections(
    values: list[ExtractedValue], corrections: list[dict]
) -> list[ExtractedValue]:
    by_key = {(c["field"], c["employee_id"]): c for c in corrections}
    matched = set()

    corrected = []
    for value in values:
        key = (value.field, value.employee_id)
        correction = by_key.get(key)
        if correction is None:
            corrected.append(value)
            continue
        matched.add(key)
        corrected.append(
            value.model_copy(
                update={
                    "value": Decimal(correction["value"]),
                    "confidence": 1.0,  # a person checked it against the document
                    "corrected_by": correction["by"],
                }
            )
        )

    # A correction that matches nothing is a mistake: fail loudly, never drop it
    unmatched = sorted(set(by_key) - matched, key=str)
    if unmatched:
        raise ValueError(f"corrections match no extracted value: {unmatched}")
    return corrected
