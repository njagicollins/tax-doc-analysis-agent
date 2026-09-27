"""Ingestion: pull every source's documents for a quarter into the raw zone."""

from dataclasses import dataclass, field
from pathlib import Path

from taxagent.ingestion.manifest import MANIFEST_PATH, append_row, make_row, new_run_id
from taxagent.ingestion.raw_store import RAW_DIR, store_raw
from taxagent.ingestion.sources import DocumentSource


@dataclass
class IngestResult:
    run_id: str
    new: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)


def ingest(
    quarter: str,
    sources: list[DocumentSource],
    raw_dir: Path = RAW_DIR,
    manifest_path: Path = MANIFEST_PATH,
) -> IngestResult:
    result = IngestResult(run_id=new_run_id())

    for source in sources:
        for name, content in source.fetch_documents(quarter):
            # Any stored file named <12-char hash>_<name> is an earlier version
            earlier = list((raw_dir / quarter).glob(f"{'?' * 12}_{name}"))
            stored = store_raw(content, name, quarter, raw_dir)
            append_row(
                make_row(result.run_id, source.name, name, stored), manifest_path
            )

            if not stored.is_new:
                result.unchanged.append(name)
            elif earlier:
                result.changed.append(name)  # changed after we first received it
            else:
                result.new.append(name)

    return result
