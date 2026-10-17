"""The audit log: an append-only list of events, each chained to the one before.

Every entry stores the hash of the entry before it. Change, remove or reorder
any line and the hashes after it stop matching, so tampering shows.
"""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from taxagent.ingestion.raw_store import sha256_of

AUDIT_PATH = Path("data/audit/audit.jsonl")
FIRST = "0" * 64  # what the first entry points back to: there is nothing before it
# One writer at a time: two entries written at once would both follow the same entry
WRITING = threading.Lock()


def entry_hash(entry: dict) -> str:
    """The hash of everything in the entry except the hash itself."""
    body = {key: value for key, value in entry.items() if key != "hash"}
    # sort_keys: the same entry must always turn into the same text
    return sha256_of(json.dumps(body, sort_keys=True).encode("utf-8"))


def read_entries(path: Path = AUDIT_PATH) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def append_event(
    event: str, actor: str, details: dict, path: Path = AUDIT_PATH
) -> dict:
    """Add one event to the end of the log and return the saved entry."""
    with WRITING:
        entries = read_entries(path)
        entry = {
            "seq": len(entries) + 1,
            "at": datetime.now(UTC).isoformat(),
            "event": event,
            "actor": actor,
            "details": details,
            "prev_hash": entries[-1]["hash"] if entries else FIRST,
        }
        entry["hash"] = entry_hash(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:  # "a" = append only
            f.write(json.dumps(entry) + "\n")
    return entry


def verify(path: Path = AUDIT_PATH, last_hash: str | None = None) -> list[str]:
    """Everything wrong with the log. An empty list means it is intact.

    `last_hash` is the newest entry's hash, kept somewhere else. Without it,
    entries cut off the END of the log cannot be noticed: nothing after them
    is left to disagree.
    """
    problems = []
    previous = FIRST
    for number, entry in enumerate(read_entries(path), start=1):
        if entry["seq"] != number:
            problems.append(f"entry {number} is numbered {entry['seq']}")
        if entry["prev_hash"] != previous:
            problems.append(f"entry {number} does not follow the entry before it")
        if entry["hash"] != entry_hash(entry):
            problems.append(f"entry {number} was changed after it was written")
        previous = entry["hash"]
    if last_hash is not None and previous != last_hash:
        problems.append("the log does not end where the outside copy says it should")
    return problems
