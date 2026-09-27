"""Run every extractor over the latest stored version of each document."""

from dataclasses import dataclass
from pathlib import Path

from taxagent.extraction.csv_snapshot import extract_payroll_snapshot
from taxagent.extraction.excel import extract_register
from taxagent.extraction.pdf import extract_941, extract_w2
from taxagent.ingestion.manifest import MANIFEST_PATH, ManifestRow, read_rows
from taxagent.ingestion.raw_store import TamperedFileError, sha256_of
from taxagent.schema.models import ExtractedValue

EXTRACTED_DIR = Path("data/extracted")
REVIEW_THRESHOLD = 0.95  # below this, a human must check the value


@dataclass
class ExtractionResult:
    values: list[ExtractedValue]
    needs_review: list[ExtractedValue]
    output_path: Path


def latest_documents(quarter: str, manifest_path: Path) -> list[ManifestRow]:
    """The manifest is in time order, so a later row for the same document wins."""
    latest: dict[tuple[str, str], ManifestRow] = {}
    for row in read_rows(manifest_path):
        if Path(row.path).parent.name == quarter:
            latest[(row.source, row.name)] = row
    return list(latest.values())


def extract_document(row: ManifestRow) -> list[ExtractedValue]:
    path = Path(row.path)
    # Evidence check: never extract from a file that no longer matches its receipt
    if sha256_of(path.read_bytes()) != row.sha256:
        raise TamperedFileError(f"{path} does not match the manifest")

    if row.name.startswith("payroll_register_"):
        return extract_register(path, row.sha256)
    if row.name.startswith("form_941_"):
        return extract_941(path, row.sha256)
    if row.name.startswith("w2_"):
        return extract_w2(path, row.sha256, employee_id_hint=path.stem.split("_")[-1])
    if row.name.startswith("payroll_db_"):
        return extract_payroll_snapshot(path, row.sha256)
    raise ValueError(f"No extractor for document {row.name!r}")


def run_extraction(
    quarter: str,
    manifest_path: Path = MANIFEST_PATH,
    extracted_dir: Path = EXTRACTED_DIR,
) -> ExtractionResult:
    values = [
        value
        for row in latest_documents(quarter, manifest_path)
        for value in extract_document(row)
    ]

    # Derived data: safe to rebuild from the raw zone at any time
    output_path = extracted_dir / quarter / "values.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(value.model_dump_json() + "\n" for value in values), encoding="utf-8"
    )

    needs_review = [v for v in values if v.confidence < REVIEW_THRESHOLD]
    return ExtractionResult(values, needs_review, output_path)
