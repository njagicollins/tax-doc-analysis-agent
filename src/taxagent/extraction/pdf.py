"""Read 941 and W-2 PDFs: find each label, then take the numbers to its right.

A PDF has no fields, only words placed on a page. So we infer: words that share
a baseline form a row, and a number on the same row as a label belongs to it.
"""

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf

from taxagent.schema.models import ExtractedValue, SourceRef

TEXT_LAYER_CONFIDENCE = 0.98  # exact characters, but the label match is inferred

# Label on the form -> field names, one per number column (left to right)
FORM_941_LINES = {
    "Number of employees who received wages": ["form_941.line_1"],
    "Wages, tips, and other compensation": ["form_941.line_2"],
    "Federal income tax withheld": ["form_941.line_3"],
    "Taxable social security wages": [
        "form_941.line_5a_wages",
        "form_941.line_5a_tax",
    ],
    "Taxable Medicare wages": ["form_941.line_5c_wages", "form_941.line_5c_tax"],
    "Total social security and Medicare taxes": ["form_941.line_5e"],
    "Total taxes before adjustments": ["form_941.line_6"],
}

W2_BOXES = {
    "Wages, tips, other compensation": ["w2.box_1"],
    "Federal income tax withheld": ["w2.box_2"],
    "Social security wages": ["w2.box_3"],
    "Social security tax withheld": ["w2.box_4"],
    "Medicare wages and tips": ["w2.box_5"],
    "Medicare tax withheld": ["w2.box_6"],
}

EMPLOYEE_ID = re.compile(r"\bID:\s*(E\d{3})\b")

Word = tuple[float, float, float, float, str]  # x0, y0, x1, y1, text


def to_number(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def rows_of(page: pymupdf.Page) -> list[list[Word]]:
    """Group words into visual rows by their baseline, left to right."""
    rows: dict[int, list[Word]] = {}
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        rows.setdefault(round(y1), []).append((x0, y0, x1, y1, text))
    return [sorted(row) for _, row in sorted(rows.items())]


def extract_fields(
    path: Path,
    file_sha256: str,
    labels: dict[str, list[str]],
    employee_id: str | None = None,
) -> list[ExtractedValue]:
    page = pymupdf.open(path)[0]
    rows = rows_of(page)
    found: dict[str, ExtractedValue] = {}

    for row in rows:
        line_text = " ".join(word[4] for word in row)
        for label, fields in labels.items():
            if label not in line_text:
                continue
            numbers = [w for w in row if to_number(w[4]) is not None]
            # The first "number" may be the line number (e.g. "2"), so take the last ones
            for field, word in zip(fields, numbers[-len(fields) :]):
                found[field] = ExtractedValue(
                    field=field,
                    employee_id=employee_id,
                    value=to_number(word[4]),
                    confidence=TEXT_LAYER_CONFIDENCE,
                    source=SourceRef(file_sha256=file_sha256, page=1, bbox=word[:4]),
                )

    # Anything we couldn't find is reported as unreadable, never guessed
    unreadable = SourceRef(file_sha256=file_sha256, page=1)
    return [
        found.get(field)
        or ExtractedValue(
            field=field,
            employee_id=employee_id,
            value=None,
            confidence=0.0,
            source=unreadable,
        )
        for fields in labels.values()
        for field in fields
    ]


def extract_941(path: Path, file_sha256: str) -> list[ExtractedValue]:
    return extract_fields(path, file_sha256, FORM_941_LINES)


def extract_w2(
    path: Path, file_sha256: str, employee_id_hint: str | None = None
) -> list[ExtractedValue]:
    """The ID printed on the form wins; the hint (from the file name) is a fallback."""
    match = EMPLOYEE_ID.search(pymupdf.open(path)[0].get_text())
    employee_id = match.group(1) if match else employee_id_hint
    return extract_fields(path, file_sha256, W2_BOXES, employee_id)
