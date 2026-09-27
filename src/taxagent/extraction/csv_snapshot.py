"""Read the SQL payroll snapshot (CSV). Like Excel: exact cells, so full confidence."""

import csv
import io
from decimal import Decimal
from pathlib import Path

from openpyxl.utils import get_column_letter

from taxagent.schema.models import ExtractedValue, SourceRef

# CSV column -> canonical field name. The database stores whole cents.
CENT_COLUMNS = {
    "regular_wages_cents": "payroll_db.regular_wages",
    "bonus_cents": "payroll_db.bonus",
    "gross_wages_cents": "payroll_db.gross_wages",
    "federal_tax_cents": "payroll_db.federal_tax",
    "ss_tax_cents": "payroll_db.ss_tax",
    "medicare_tax_cents": "payroll_db.medicare_tax",
}


def extract_payroll_snapshot(path: Path, file_sha256: str) -> list[ExtractedValue]:
    reader = csv.reader(io.StringIO(path.read_text(encoding="utf-8")))
    header = next(reader)

    values = []
    for row_number, row in enumerate(reader, start=2):  # row 1 is the header
        record = dict(zip(header, row, strict=True))
        for column_number, column in enumerate(header, start=1):
            field = CENT_COLUMNS.get(column)
            if field is None:
                continue
            values.append(
                ExtractedValue(
                    field=field,
                    employee_id=record["employee_id"],
                    value=Decimal(record[column]) / 100,
                    confidence=1.0,
                    source=SourceRef(
                        file_sha256=file_sha256,
                        cell=f"{get_column_letter(column_number)}{row_number}",
                    ),
                )
            )
    return values
