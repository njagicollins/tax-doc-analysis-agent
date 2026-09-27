from datetime import datetime

from taxagent.ingestion.manifest import append_row, make_row, new_run_id, read_rows
from taxagent.ingestion.raw_store import store_raw


def test_rows_are_appended_and_read_back(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    run_id = new_run_id()
    first = store_raw(b"941", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    second = store_raw(b"w2", "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)

    append_row(make_row(run_id, "adp", "form_941.pdf", first), manifest)
    append_row(make_row(run_id, "adp", "w2_E001.pdf", second), manifest)

    rows = read_rows(manifest)
    assert [row.name for row in rows] == ["form_941.pdf", "w2_E001.pdf"]
    assert rows[0].sha256 == first.sha256
    assert all(row.run_id == run_id for row in rows)


def test_a_second_run_keeps_the_first_runs_rows(tmp_path):
    manifest = tmp_path / "manifest.jsonl"
    stored = store_raw(b"941", "form_941.pdf", "2026Q2", raw_dir=tmp_path)

    append_row(make_row("run-1", "adp", "form_941.pdf", stored), manifest)
    again = store_raw(b"941", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    append_row(make_row("run-2", "adp", "form_941.pdf", again), manifest)

    rows = read_rows(manifest)
    assert [(row.run_id, row.is_new) for row in rows] == [
        ("run-1", True),
        ("run-2", False),
    ]


def test_fetched_at_is_utc(tmp_path):
    stored = store_raw(b"941", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    row = make_row("run-1", "adp", "form_941.pdf", stored)

    assert datetime.fromisoformat(row.fetched_at).utcoffset().total_seconds() == 0


def test_missing_manifest_reads_as_empty(tmp_path):
    assert read_rows(tmp_path / "nope.jsonl") == []
