from taxagent.ingestion.manifest import read_rows
from taxagent.ingestion.pipeline import ingest


class FakeSource:
    """Stands in for ADP or SQL: no network, no database."""

    def __init__(self, name: str, documents: list[tuple[str, bytes]]) -> None:
        self.name = name
        self.documents = documents

    def fetch_documents(self, quarter: str) -> list[tuple[str, bytes]]:
        return self.documents


def run(tmp_path, *sources):
    return ingest(
        "2026Q2",
        list(sources),
        raw_dir=tmp_path / "raw",
        manifest_path=tmp_path / "manifest.jsonl",
    )


def test_first_run_stores_everything_as_new(tmp_path):
    adp = FakeSource("adp", [("form_941.pdf", b"941"), ("w2_E001.pdf", b"w2")])
    sql = FakeSource("sql", [("payroll_db.csv", b"csv")])

    result = run(tmp_path, adp, sql)

    assert result.new == ["form_941.pdf", "w2_E001.pdf", "payroll_db.csv"]
    assert len(read_rows(tmp_path / "manifest.jsonl")) == 3


def test_second_identical_run_stores_nothing_new(tmp_path):
    adp = FakeSource("adp", [("form_941.pdf", b"941")])
    first = run(tmp_path, adp)
    second = run(tmp_path, adp)

    assert second.unchanged == ["form_941.pdf"]
    assert len(list((tmp_path / "raw" / "2026Q2").iterdir())) == 1
    assert [row.run_id for row in read_rows(tmp_path / "manifest.jsonl")] == [
        first.run_id,
        second.run_id,
    ]


def test_changed_document_is_reported_and_both_versions_kept(tmp_path):
    run(tmp_path, FakeSource("adp", [("form_941.pdf", b"941 original")]))
    result = run(tmp_path, FakeSource("adp", [("form_941.pdf", b"941 amended")]))

    assert result.changed == ["form_941.pdf"]
    assert len(list((tmp_path / "raw" / "2026Q2").iterdir())) == 2
