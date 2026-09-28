from decimal import Decimal

import pytest

from taxagent.compute.run import FINDING_JSON, previous_quarter, run_compute
from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "1" * 64


def value(field, amount, employee_id=None):
    return ExtractedValue(
        field=field,
        employee_id=employee_id,
        value=Decimal(amount),
        confidence=1.0,
        source=SourceRef(file_sha256=HASH, cell="A1"),
    )


def save(extracted_dir, quarter, values):
    path = extracted_dir / quarter / "values.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(v.model_dump_json() + "\n" for v in values))


def quarter_values(e001_wages, line_2):
    return [
        value("register.gross_wages", e001_wages, "E001"),
        value("payroll_db.gross_wages", e001_wages, "E001"),
        value("form_941.line_2", line_2),
    ]


@pytest.mark.parametrize(
    ("quarter", "expected"),
    [("2026Q2", "2026Q1"), ("2026Q4", "2026Q3"), ("2026Q1", "2025Q4")],
)
def test_previous_quarter(quarter, expected):
    assert previous_quarter(quarter) == expected


def test_compares_with_the_previous_quarter_when_available(tmp_path):
    save(tmp_path, "2026Q1", quarter_values("1000", "1000"))
    save(tmp_path, "2026Q2", quarter_values("2000", "2000"))

    result = run_compute("2026Q2", tmp_path, tmp_path / "findings")

    assert result.compared_with == "2026Q1"
    [jump] = result.findings
    assert (jump.kind, jump.change_pct) == ("variance", Decimal("100.00"))


def test_without_a_previous_quarter_variance_is_skipped(tmp_path):
    save(tmp_path, "2026Q2", quarter_values("2000", "2000"))

    result = run_compute("2026Q2", tmp_path, tmp_path / "findings")

    assert result.compared_with is None
    assert result.findings == []


def test_findings_are_saved_and_load_back(tmp_path):
    save(tmp_path, "2026Q2", quarter_values("2000", "2270"))

    result = run_compute("2026Q2", tmp_path, tmp_path / "findings")

    [line] = result.output_path.read_text(encoding="utf-8").splitlines()
    assert FINDING_JSON.validate_json(line) == result.findings[0]


def test_missing_extraction_says_what_to_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="taxagent extract --quarter 2026Q2"):
        run_compute("2026Q2", tmp_path, tmp_path / "findings")
