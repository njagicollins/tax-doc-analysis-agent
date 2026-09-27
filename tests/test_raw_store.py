import pytest

from taxagent.ingestion.raw_store import TamperedFileError, sha256_of, store_raw


def test_new_file_is_stored_under_its_hash(tmp_path):
    stored = store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)

    assert stored.is_new
    assert stored.sha256 == sha256_of(b"941 v1")
    assert stored.path.name == f"{stored.sha256[:12]}_form_941.pdf"
    assert stored.path.read_bytes() == b"941 v1"


def test_same_content_twice_is_stored_once(tmp_path):
    store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    again = store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)

    assert not again.is_new
    assert len(list((tmp_path / "2026Q2").iterdir())) == 1


def test_changed_content_is_kept_next_to_the_original(tmp_path):
    first = store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    second = store_raw(b"941 v2", "form_941.pdf", "2026Q2", raw_dir=tmp_path)

    assert second.is_new
    assert first.path.read_bytes() == b"941 v1"
    assert len(list((tmp_path / "2026Q2").iterdir())) == 2


def test_stored_file_is_read_only(tmp_path):
    stored = store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)

    with pytest.raises(PermissionError):
        stored.path.write_bytes(b"edited")


def test_tampering_is_detected(tmp_path):
    stored = store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)
    stored.path.chmod(0o644)
    stored.path.write_bytes(b"secretly edited")

    with pytest.raises(TamperedFileError):
        store_raw(b"941 v1", "form_941.pdf", "2026Q2", raw_dir=tmp_path)


def test_names_with_paths_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        store_raw(b"x", "../../.env", "2026Q2", raw_dir=tmp_path)
