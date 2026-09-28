from decimal import Decimal

import pytest

from synthetic.__main__ import main as generate_everything
from taxagent.compute.findings import employee_list_findings, run_checks
from taxagent.extraction.csv_snapshot import extract_payroll_snapshot
from taxagent.extraction.excel import extract_register
from taxagent.extraction.pdf import extract_941
from taxagent.ingestion.sources import SqlPayrollSource
from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "0" * 64


@pytest.fixture(scope="module")
def extracted(tmp_path_factory):
    """Real generated documents -> real extractors, for both quarters."""
    folder = tmp_path_factory.mktemp("world")
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(folder)
        generate_everything()

    adp = folder / "data/sources/adp"
    sql = SqlPayrollSource(folder / "data/sources/sql/payroll.db")
    values = {}
    for quarter in ["2026Q1", "2026Q2"]:
        [(name, content)] = sql.fetch_documents(quarter)
        (folder / name).write_bytes(content)
        values[quarter] = (
            extract_register(adp / f"payroll_register_{quarter}.xlsx", HASH)
            + extract_941(adp / f"form_941_{quarter}.pdf", HASH)
            + extract_payroll_snapshot(folder / name, HASH)
        )
    return values


def test_q1_missing_employee_shows_up_three_ways(extracted):
    findings = run_checks("2026Q1", extracted["2026Q1"])

    assert [(f.check, f.difference) for f in findings] == [
        ("register_vs_941_wages", Decimal("37500.00")),
        ("register_vs_payroll_db_wages", Decimal("37500.00")),
        ("payroll_db_vs_register_employees", Decimal("37500.00")),
    ]
    assert findings[2].employee_id == "E013"


def test_q2_catches_the_typo_and_the_bonus(extracted):
    findings = run_checks("2026Q2", extracted["2026Q2"], extracted["2026Q1"])

    typo, bonus = findings
    assert (typo.check, typo.difference) == ("register_vs_941_wages", Decimal("270.00"))
    assert (bonus.employee_id, bonus.change_pct) == ("E007", Decimal("40.00"))


def test_every_finding_carries_evidence(extracted):
    findings = run_checks("2026Q2", extracted["2026Q2"], extracted["2026Q1"])

    assert all(f.sources for f in findings)


def test_ghost_employee_is_flagged():
    def value(field, employee_id):
        return ExtractedValue(
            field=field,
            employee_id=employee_id,
            value=Decimal(1000),
            confidence=1.0,
            source=SourceRef(file_sha256=HASH, cell="A1"),
        )

    values = [
        value("register.gross_wages", "E001"),
        value("register.gross_wages", "E999"),
        value("payroll_db.gross_wages", "E001"),
    ]

    [ghost] = employee_list_findings("2026Q2", values)
    assert (ghost.kind, ghost.employee_id) == ("extra_employee", "E999")
