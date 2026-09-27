"""Command-line entry point, e.g. uv run taxagent ingest --quarter 2026Q2"""

import argparse
import os
import re
from pathlib import Path

import httpx2
from dotenv import load_dotenv

from taxagent.extraction.run import REVIEW_THRESHOLD, run_extraction
from taxagent.ingestion.pipeline import ingest
from taxagent.ingestion.sources import AdpApiSource, SqlPayrollSource

QUARTER_PATTERN = re.compile(r"^\d{4}Q[1-4]$")


def quarter_arg(value: str) -> str:
    if not QUARTER_PATTERN.match(value):
        raise argparse.ArgumentTypeError(
            f"expected a quarter like 2026Q2, got {value!r}"
        )
    return value


def run_ingest(quarter: str) -> None:
    base_url = os.environ["ADP_BASE_URL"]
    sources = [
        AdpApiSource(base_url, os.environ["ADP_API_KEY"]),
        SqlPayrollSource(Path(os.environ["PAYROLL_DB_PATH"])),
    ]

    try:
        result = ingest(quarter, sources)
    except httpx2.ConnectError:
        raise SystemExit(f"Cannot reach ADP at {base_url}. Is the server running?")

    print(
        f"Run {result.run_id}: {len(result.new)} new, "
        f"{len(result.unchanged)} unchanged, {len(result.changed)} changed"
    )
    for name in result.changed:
        print(f"  CHANGED since an earlier run: {name}")


def run_extract(quarter: str) -> None:
    result = run_extraction(quarter)
    print(f"Extracted {len(result.values)} values -> {result.output_path}")
    print(
        f"{len(result.needs_review)} need human review (confidence < {REVIEW_THRESHOLD}):"
    )
    for value in result.needs_review:
        who = value.employee_id or "company"
        print(f"  {value.field:<22} {who:<8} confidence {value.confidence}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="taxagent")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_command = commands.add_parser(
        "ingest", help="Pull a quarter's documents into the raw zone"
    )
    ingest_command.add_argument("--quarter", required=True, type=quarter_arg)
    extract_command = commands.add_parser(
        "extract", help="Read every stored document into values with evidence"
    )
    extract_command.add_argument("--quarter", required=True, type=quarter_arg)

    args = parser.parse_args(argv)
    if args.command == "ingest":
        run_ingest(args.quarter)
    elif args.command == "extract":
        run_extract(args.quarter)
