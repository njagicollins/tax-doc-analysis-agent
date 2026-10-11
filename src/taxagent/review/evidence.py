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
INK = 200  # a pixel darker than this is ink, not paper (0 = black, 255 = white)
MARGIN = 20  # points of paper kept below the last line


def raw_file(source: SourceRef, raw_dir: Path = RAW_DIR) -> Path:
    """The stored file this value was read from, verified against its hash.

    Files are named by their hash, so any quarter's folder will do: last
    quarter's register is evidence for this quarter's variance.
    """
    matches = list(raw_dir.glob(f"*/{source.file_sha256[:12]}_*"))
    if not matches:
        raise FileNotFoundError(f"No raw file for {source.file_sha256[:12]}")
    path = matches[0]
    if sha256_of(path.read_bytes()) != source.file_sha256:
        raise TamperedFileError(f"{path} no longer matches its hash")
    return path


def location(source: SourceRef, raw_dir: Path = RAW_DIR) -> str:
    """Where a value is, in words a reviewer can follow: the file, then page or cell."""
    place = f"page {source.page}" if source.page else f"{source.sheet}!{source.cell}"
    return f"{raw_file(source, raw_dir).name}, {place}"


def last_ink(picture: pymupdf.Pixmap) -> int:
    """The lowest row of pixels with anything on it (the last row if the page is blank)."""
    width = picture.stride  # bytes in one row
    for row in range(picture.height - 1, -1, -1):
        if min(picture.samples[row * width : (row + 1) * width]) < INK:
            return row
    return picture.height - 1


def page_image(path: Path, source: SourceRef) -> bytes:
    """The PDF page as a PNG, with the value's box outlined when we know where it is.

    The empty paper below the last line is cut off, so a half-empty page does not
    push the rest of the screen out of sight. Nothing with ink on it is removed.
    """
    page = pymupdf.open(path)[source.page - 1]
    if source.bbox:
        page.draw_rect(source.bbox, color=HIGHLIGHT, width=2)  # in memory only
    bottom = last_ink(page.get_pixmap(dpi=DPI)) * 72 / DPI + MARGIN  # pixels -> points
    used = pymupdf.Rect(0, 0, page.rect.width, min(bottom, page.rect.height))
    return page.get_pixmap(dpi=DPI, clip=used).tobytes("png")
