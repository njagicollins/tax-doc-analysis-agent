import pymupdf
import pytest

from taxagent.ingestion.raw_store import TamperedFileError, store_raw
from taxagent.review.evidence import page_image, raw_file
from taxagent.schema.models import SourceRef

PNG_START = b"\x89PNG"


def a_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "1  Wages, tips, other compensation  63,250.00")
    return doc.tobytes()


def test_the_source_file_is_found_by_its_hash(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    source = SourceRef(file_sha256=stored.sha256, page=1)

    assert raw_file(source, "2026Q2", raw_dir=tmp_path) == stored.path


def test_a_missing_source_file_fails_clearly(tmp_path):
    source = SourceRef(file_sha256="0" * 64, page=1)

    with pytest.raises(FileNotFoundError, match="000000000000"):
        raw_file(source, "2026Q2", raw_dir=tmp_path)


def test_a_changed_source_file_is_refused(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    stored.path.chmod(0o644)
    stored.path.write_bytes(b"not the original")

    with pytest.raises(TamperedFileError):
        raw_file(SourceRef(file_sha256=stored.sha256, page=1), "2026Q2", tmp_path)


def test_the_value_is_outlined_when_its_box_is_known(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    plain = SourceRef(file_sha256=stored.sha256, page=1)
    boxed = SourceRef(file_sha256=stored.sha256, page=1, bbox=(60, 55, 300, 80))

    without_box = page_image(stored.path, plain)
    with_box = page_image(stored.path, boxed)

    assert without_box.startswith(PNG_START) and with_box.startswith(PNG_START)
    assert with_box != without_box
