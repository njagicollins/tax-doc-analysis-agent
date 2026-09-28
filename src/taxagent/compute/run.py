"""Load a quarter's extracted values, run every check, save the findings."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from taxagent.compute.findings import Finding, run_checks
from taxagent.extraction.run import EXTRACTED_DIR
from taxagent.schema.models import ExtractedValue

FINDINGS_DIR = Path("data/findings")
FINDING_JSON = TypeAdapter(Finding)  # lets Pydantic save and load our dataclass


@dataclass
class ComputeResult:
    findings: list[Finding]
    compared_with: str | None  # previous quarter, if its values were available
    output_path: Path


def previous_quarter(quarter: str) -> str:
    year, number = int(quarter[:4]), int(quarter[-1])
    return f"{year}Q{number - 1}" if number > 1 else f"{year - 1}Q4"


def load_values(path: Path) -> list[ExtractedValue] | None:
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ExtractedValue.model_validate_json(line) for line in lines]


def run_compute(
    quarter: str,
    extracted_dir: Path = EXTRACTED_DIR,
    findings_dir: Path = FINDINGS_DIR,
) -> ComputeResult:
    current = load_values(extracted_dir / quarter / "values.jsonl")
    if current is None:
        raise FileNotFoundError(
            f"No extracted values for {quarter}. "
            f"Run: taxagent extract --quarter {quarter}"
        )

    earlier = previous_quarter(quarter)
    previous = load_values(extracted_dir / earlier / "values.jsonl")
    findings = run_checks(quarter, current, previous)

    output_path = findings_dir / quarter / "findings.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(FINDING_JSON.dump_json(f).decode() + "\n" for f in findings),
        encoding="utf-8",
    )
    return ComputeResult(findings, earlier if previous else None, output_path)
