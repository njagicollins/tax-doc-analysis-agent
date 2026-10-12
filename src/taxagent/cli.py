"""Command-line entry point, e.g. uv run taxagent ingest --quarter 2026Q2"""

import argparse
import json
import os
import re
from pathlib import Path

import httpx2
from dotenv import load_dotenv

from taxagent.agent.runner import resume_run, run_status, start_run
from taxagent.audit.log import append_event
from taxagent.compute.run import run_compute
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
    append_event(
        "files_ingested",
        "cli",
        {
            "ingest_run": result.run_id,
            "quarter": quarter,
            "new": len(result.new),
            "unchanged": len(result.unchanged),
            "changed": result.changed,  # by name: a changed document is worth a look
        },
    )

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


def run_compute_command(quarter: str) -> None:
    try:
        result = run_compute(quarter)
    except FileNotFoundError as error:
        raise SystemExit(str(error))

    if result.compared_with:
        print(f"Compared with {result.compared_with}")
    else:
        print("No previous quarter extracted: variance checks skipped")
    print(f"{len(result.findings)} findings -> {result.output_path}")
    for finding in result.findings:
        print(f"  [{finding.kind}] {finding.summary}")


def show_run(run: dict) -> None:
    print(f"Run {run['run_id']}: {run['status']}")
    if run["pending"] is None:
        print("Not waiting for anyone.")
        return
    print("Waiting for a person. Request:")
    print(json.dumps(run["pending"], indent=2))
    print(f"Answer with: taxagent resume --run {run['run_id']} --answer answer.json")


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

    compute_command = commands.add_parser(
        "compute", help="Reconcile documents and flag unusual changes"
    )
    compute_command.add_argument("--quarter", required=True, type=quarter_arg)

    run_command = commands.add_parser(
        "run", help="Start the full workflow; it pauses when a person is needed"
    )
    run_command.add_argument("--quarter", required=True, type=quarter_arg)

    status_command = commands.add_parser(
        "status", help="Show what a run is waiting for"
    )
    status_command.add_argument("--run", required=True)

    resume_command = commands.add_parser("resume", help="Answer a paused run")
    resume_command.add_argument("--run", required=True)
    resume_command.add_argument("--answer", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "ingest":
        run_ingest(args.quarter)
    elif args.command == "extract":
        run_extract(args.quarter)
    elif args.command == "compute":
        run_compute_command(args.quarter)
    elif args.command == "run":
        show_run(start_run(args.quarter, actor="cli"))
    elif args.command == "status":
        show_run(run_status(args.run))
    elif args.command == "resume":
        answer = json.loads(args.answer.read_text(encoding="utf-8"))
        show_run(resume_run(args.run, answer))
