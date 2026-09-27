import sqlite3

import httpx2
import pytest
from fastapi.testclient import TestClient

from mock_sources import adp_api
from mock_sources.seed_db import seed_database
from synthetic.employees import generate_employees
from synthetic.payroll import generate_payroll
from taxagent.ingestion.sources import AdpApiSource, SqlPayrollSource


@pytest.fixture
def adp(tmp_path, monkeypatch):
    (tmp_path / "form_941_2026Q1.pdf").write_bytes(b"q1")
    (tmp_path / "form_941_2026Q2.pdf").write_bytes(b"q2")
    (tmp_path / "w2_2026_E001.pdf").write_bytes(b"w2")
    monkeypatch.setattr(adp_api, "DOCUMENTS_DIR", tmp_path)
    return TestClient(adp_api.app)


def test_fetches_only_the_quarters_documents(adp):
    source = AdpApiSource("unused", adp_api.API_KEY, client=adp)

    documents = source.fetch_documents("2026Q2")

    assert documents == [("form_941_2026Q2.pdf", b"q2"), ("w2_2026_E001.pdf", b"w2")]


def test_wrong_key_fails_loudly(adp):
    source = AdpApiSource("unused", "wrong-key", client=adp)

    with pytest.raises(httpx2.HTTPStatusError):
        source.fetch_documents("2026Q2")


@pytest.fixture
def payroll_db(tmp_path):
    employees = generate_employees()
    return seed_database(employees, generate_payroll(employees), tmp_path / "p.db")


def test_sql_export_has_one_row_per_employee(payroll_db):
    [(name, content)] = SqlPayrollSource(payroll_db).fetch_documents("2026Q1")
    lines = content.decode("utf-8").splitlines()

    assert name == "payroll_db_2026Q1.csv"
    assert lines[0].startswith("employee_id,name,ssn,quarter")
    assert len(lines) == 1 + 20  # header + every employee, E013 included


def test_sql_export_is_byte_identical_every_time(payroll_db):
    source = SqlPayrollSource(payroll_db)

    assert source.fetch_documents("2026Q2") == source.fetch_documents("2026Q2")


def test_sql_source_cannot_write_to_the_database(payroll_db, monkeypatch):
    source = SqlPayrollSource(payroll_db)
    monkeypatch.setattr(
        "taxagent.ingestion.sources.PAYROLL_EXPORT_SQL",
        "DELETE FROM payroll WHERE quarter = ?",
    )

    with pytest.raises(sqlite3.OperationalError):
        source.fetch_documents("2026Q2")
