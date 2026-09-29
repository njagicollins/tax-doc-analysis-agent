"""The canonical schema: one shape for every extracted value, whatever file it came from."""

from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SourceRef(BaseModel):
    """Where exactly a value came from. If it can't be traced, it can't be used."""

    model_config = ConfigDict(frozen=True)

    file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # PDFs: page number + bounding box (x0, y0, x1, y1) in points
    page: int | None = Field(default=None, ge=1)
    bbox: tuple[float, float, float, float] | None = None
    # Excel / CSV: sheet name + cell address
    sheet: str | None = None
    cell: str | None = None

    @model_validator(mode="after")
    def points_somewhere(self) -> Self:
        in_pdf = self.page is not None
        in_sheet = self.cell is not None
        if in_pdf == in_sheet:
            raise ValueError("a SourceRef needs either a PDF page or a sheet cell")
        return self


class ExtractedValue(BaseModel):
    """One number read from one document, with its evidence."""

    model_config = ConfigDict(frozen=True)

    field: str
    employee_id: str | None = None  # None for company-level values (e.g. 941 lines)
    value: Decimal | None  # None = we couldn't read it (e.g. a scan)
    confidence: float = Field(ge=0, le=1)
    source: SourceRef
    corrected_by: str | None = None  # set when a human typed in the value
