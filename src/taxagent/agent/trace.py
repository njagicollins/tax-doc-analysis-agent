"""A trace: one line per finished step, saying how long it took and what it did.

Every workflow step is wrapped by `traced`, so the lines are written as the run
happens and saved with it. Reading a trace later never re-runs anything.
"""

import inspect
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from taxagent.ingestion.manifest import ManifestRow


def traced(name: str, node: Callable) -> Callable:
    """Wrap a step so it leaves one line in the run's trace.

    The step says what it did by returning a "did" sentence, and may add "notes":
    the decisions it made and why. This wrapper takes both out, adds the timing,
    and puts the line in the trace.
    """
    takes_config = len(inspect.signature(node).parameters) == 2

    def step(state, config):
        started = time.perf_counter()  # a stopwatch: not affected by clock changes
        update = node(state, config) if takes_config else node(state)
        line = {
            "step": name,
            "seconds": round(time.perf_counter() - started, 3),
            "finished_at": datetime.now(UTC).isoformat(),
            "did": update.pop("did"),
            "notes": update.pop("notes", []),
        }
        return {**update, "trace": [line]}

    return step


def ingest_line(quarter: str, rows: list[ManifestRow], before: str) -> dict | None:
    """The trace line for the last ingest of this quarter that the run could have used.

    Ingest runs as its own command, so its line is rebuilt from the manifest: the
    files of one ingest share a run id, and each has the time it was fetched.
    """
    mine = [
        row
        for row in rows
        if Path(row.path).parent.name == quarter and row.fetched_at <= before
    ]
    if not mine:
        return None
    last = [row for row in mine if row.run_id == mine[-1].run_id]
    times = [datetime.fromisoformat(row.fetched_at) for row in last]
    new = sum(row.is_new for row in last)
    return {
        "step": "ingest",
        "seconds": round((max(times) - min(times)).total_seconds(), 3),
        "finished_at": max(times).isoformat(),
        "did": f"Fetched {len(last)} files: {new} new, {len(last) - new} unchanged",
    }


def with_waits(lines: list[dict], human_steps: set[str]) -> dict[str, dict]:
    """Each line by step name. Steps that wait for a person also get "waited".

    A person's step takes almost no machine time; what matters is how long the
    run sat waiting. That is the gap since the step before it finished.
    """
    by_step = {}
    for previous, line in zip([None, *lines], lines, strict=False):
        waited = None
        if previous and line["step"] in human_steps:
            gap = datetime.fromisoformat(line["finished_at"]) - datetime.fromisoformat(
                previous["finished_at"]
            )
            waited = max(gap.total_seconds() - line["seconds"], 0)
        by_step[line["step"]] = {**line, "waited": waited}
    return by_step


def duration(seconds: float) -> str:
    """Seconds in the unit a person would say: 120 ms, 4.2 s, 3 min 12 s, 2 h 5 min."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes} min {rest} s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h"
