import pymupdf
import pytest

from taxagent.ingestion.raw_store import TamperedFileError, store_raw
from taxagent.review.evidence import location, page_image, raw_file
from taxagent.schema.models import SourceRef

PNG_START = b"\x89PNG"


def a_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text(
        (72, 72), "1  Wages, tips, other compensation  63,250.00"
    )
    return doc.tobytes()


def test_the_source_file_is_found_by_its_hash(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    source = SourceRef(file_sha256=stored.sha256, page=1)

    assert raw_file(source, raw_dir=tmp_path) == stored.path


def test_a_missing_source_file_fails_clearly(tmp_path):
    source = SourceRef(file_sha256="0" * 64, page=1)

    with pytest.raises(FileNotFoundError, match="000000000000"):
        raw_file(source, raw_dir=tmp_path)


def test_a_changed_source_file_is_refused(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    stored.path.chmod(0o644)
    stored.path.write_bytes(b"not the original")

    with pytest.raises(TamperedFileError):
        raw_file(SourceRef(file_sha256=stored.sha256, page=1), raw_dir=tmp_path)


def test_the_value_is_outlined_when_its_box_is_known(tmp_path):
    stored = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    plain = SourceRef(file_sha256=stored.sha256, page=1)
    boxed = SourceRef(file_sha256=stored.sha256, page=1, bbox=(60, 55, 300, 80))

    without_box = page_image(stored.path, plain)
    with_box = page_image(stored.path, boxed)

    assert without_box.startswith(PNG_START) and with_box.startswith(PNG_START)
    assert with_box != without_box


def test_last_quarters_files_are_found_too(tmp_path):
    stored = store_raw(b"Q1 register", "register_2026Q1.xlsx", "2026Q1", tmp_path)
    source = SourceRef(file_sha256=stored.sha256, sheet="Register", cell="F10")

    assert raw_file(source, raw_dir=tmp_path) == stored.path


def test_a_location_names_the_file_and_the_page_or_cell(tmp_path):
    pdf = store_raw(a_pdf(), "w2_E001.pdf", "2026Q2", raw_dir=tmp_path)
    sheet = store_raw(b"register", "register_2026Q2.xlsx", "2026Q2", tmp_path)

    in_pdf = SourceRef(file_sha256=pdf.sha256, page=1)
    in_sheet = SourceRef(file_sha256=sheet.sha256, sheet="Register", cell="F10")

    assert location(in_pdf, tmp_path) == f"{pdf.path.name}, page 1"
    assert location(in_sheet, tmp_path) == f"{sheet.path.name}, Register!F10"
