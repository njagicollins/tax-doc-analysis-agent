"""Append-only manifest: one JSON line per file fetched, the receipt for auditors."""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from taxagent.ingestion.raw_store import StoredFile

MANIFEST_PATH = Path("data/raw/manifest.jsonl")


@dataclass(frozen=True)
class ManifestRow:
    run_id: str
    source: str
    name: str
    path: str
    sha256: str
    size_bytes: int
    is_new: bool
    fetched_at: str


def new_run_id() -> str:
    """Readable and unique, e.g. 20260927T101500Z-3f2a9c1b."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def make_row(run_id: str, source: str, name: str, stored: StoredFile) -> ManifestRow:
    return ManifestRow(
        run_id=run_id,
        source=source,
        name=name,
        path=stored.path.as_posix(),
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        is_new=stored.is_new,
        fetched_at=datetime.now(UTC).isoformat(),
    )


def append_row(row: ManifestRow, manifest_path: Path = MANIFEST_PATH) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as f:  # "a" = append only
        f.write(json.dumps(asdict(row)) + "\n")


def read_rows(manifest_path: Path = MANIFEST_PATH) -> list[ManifestRow]:
    if not manifest_path.exists():
        return []
    lines = manifest_path.read_text(encoding="utf-8").splitlines()
    return [ManifestRow(**json.loads(line)) for line in lines]
