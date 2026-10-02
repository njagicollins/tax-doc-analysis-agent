"""Who works here: employee ID -> name, used only to mask names before LLM calls.

Read from the latest payroll database snapshot in the raw zone, so the roster
comes from our own evidence, not from a live system.
"""

import csv
import io
from pathlib import Path

from taxagent.extraction.run import latest_documents
from taxagent.ingestion.manifest import MANIFEST_PATH


def load_roster(quarter: str, manifest_path: Path = MANIFEST_PATH) -> dict[str, str]:
    snapshots = [
        row
        for row in latest_documents(quarter, manifest_path)
        if row.name.startswith("payroll_db_")
    ]
    if not snapshots:
        raise FileNotFoundError(
            f"No payroll snapshot for {quarter}. Run: taxagent ingest --quarter {quarter}"
        )
    text = Path(snapshots[0].path).read_text(encoding="utf-8")
    return {
        row["employee_id"]: row["name"] for row in csv.DictReader(io.StringIO(text))
    }
