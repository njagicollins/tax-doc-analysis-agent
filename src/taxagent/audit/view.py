"""The audit log in words a person can read. Plain functions: the app only draws them."""


def run_of(entry: dict) -> str | None:
    """The run an entry belongs to (an ingest has its own run id)."""
    details = entry["details"]
    return details.get("run_id") or details.get("ingest_run")


def said(entry: dict) -> str:
    """One sentence for one entry."""
    details = entry["details"]
    match entry["event"]:
        case "files_ingested":
            changed = len(details["changed"])
            return (
                f"Ingested {details['quarter']}: {details['new']} new, "
                f"{details['unchanged']} unchanged, {changed} changed"
            )
        case "run_started":
            return f"Started a run for {details['quarter']}"
        case "answer_received":
            return f"Answered the {details['asked']} request"
        case "answer_refused":
            return "Answer refused: " + "; ".join(details["problems"])
        case "answer_out_of_date":
            return "Answer not used: the run had changed since the page was opened"
        case "step_finished":
            return f"{details['step']}: {details['did']}"
        case "run_finished":
            return f"Run {details['status']}"
    return entry["event"]  # an event added later still shows, by its name


def audit_rows(entries: list[dict], run_id: str | None = None) -> list[dict]:
    """The entries as table rows, oldest first. With a run id, only that run's."""
    return [
        {
            "#": entry["seq"],
            "when (UTC)": entry["at"][:19].replace("T", " "),
            "who": entry["actor"],
            "what": said(entry),
            "run": run_of(entry),
        }
        for entry in entries
        if run_id is None or run_of(entry) == run_id
    ]


def made_with(entries: list[dict], run_id: str) -> dict | None:
    """What produced a run, read from its run_started entry inside the chain."""
    for entry in entries:
        if entry["event"] == "run_started" and run_of(entry) == run_id:
            return entry["details"].get("made_with")
    return None
