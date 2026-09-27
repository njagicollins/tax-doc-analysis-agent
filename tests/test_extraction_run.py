import pytest

from synthetic.__main__ import main as generate_everything
from taxagent.extraction.run import run_extraction
from taxagent.ingestion.pipeline import ingest
from taxagent.ingestion.raw_store import TamperedFileError
from taxagent.ingestion.sources import SqlPayrollSource
from taxagent.schema.models import ExtractedValue


class FolderSource:
    """Serves the generated ADP files straight from disk: no server needed."""

    name = "adp"

    def __init__(self, folder):
        self.folder = folder

    def fetch_documents(self, quarter):
        return [
            (path.name, path.read_bytes())
            for path in sorted(self.folder.iterdir())
            if quarter in path.name or "w2_" in path.name
        ]


@pytest.fixture
def ingested(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the generator writes to ./data
    generate_everything()
    sources = [
        FolderSource(tmp_path / "data/sources/adp"),
        SqlPayrollSource(tmp_path / "data/sources/sql/payroll.db"),
    ]
    ingest(
        "2026Q2", sources, raw_dir=tmp_path / "raw", manifest_path=tmp_path / "m.jsonl"
    )
    return tmp_path


def run(tmp_path):
    return run_extraction(
        "2026Q2", manifest_path=tmp_path / "m.jsonl", extracted_dir=tmp_path / "out"
    )


def test_every_document_type_is_extracted(ingested):
    result = run(ingested)
    documents = {v.field.split(".")[0] for v in result.values}

    assert documents == {"register", "form_941", "w2", "payroll_db"}
    assert len(result.values) == 120 + 9 + 120 + 120


def test_only_the_scanned_w2_needs_review(ingested):
    result = run(ingested)

    assert {v.employee_id for v in result.needs_review} == {"E017"}
    assert len(result.needs_review) == 6


def test_values_are_saved_and_load_back(ingested):
    result = run(ingested)
    lines = result.output_path.read_text(encoding="utf-8").splitlines()

    assert len(lines) == len(result.values)
    assert ExtractedValue.model_validate_json(lines[0]) == result.values[0]


def test_tampered_raw_file_is_refused(ingested):
    [register] = (ingested / "raw" / "2026Q2").glob("*_payroll_register_2026Q2.xlsx")
    register.chmod(0o644)
    register.write_bytes(b"tampered")

    with pytest.raises(TamperedFileError):
        run(ingested)
