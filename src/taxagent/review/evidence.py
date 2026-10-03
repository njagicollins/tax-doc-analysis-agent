"""Show a reviewer the evidence: the source page a value came from.

Files are found by hash in the write-once raw zone and re-checked before use, so
the picture on screen is provably the document the value was read from.
"""

from pathlib import Path

import pymupdf

from taxagent.ingestion.raw_store import RAW_DIR, TamperedFileError, sha256_of
from taxagent.schema.models import SourceRef

HIGHLIGHT = (1, 0, 0)  # red, as RGB from 0 to 1
DPI = 110


def raw_file(source: SourceRef, quarter: str, raw_dir: Path = RAW_DIR) -> Path:
    """The stored file this value was read from, verified against its hash."""
    matches = list((raw_dir / quarter).glob(f"{source.file_sha256[:12]}_*"))
    if not matches:
        raise FileNotFoundError(f"No raw file for {source.file_sha256[:12]}")
    path = matches[0]
    if sha256_of(path.read_bytes()) != source.file_sha256:
        raise TamperedFileError(f"{path} no longer matches its hash")
    return path


def page_image(path: Path, source: SourceRef) -> bytes:
    """The PDF page as a PNG, with the value's box outlined when we know where it is."""
    page = pymupdf.open(path)[source.page - 1]
    if source.bbox:
        page.draw_rect(source.bbox, color=HIGHLIGHT, width=2)  # in memory only
    return page.get_pixmap(dpi=DPI).tobytes("png")
