"""Start, inspect and resume workflow runs that are saved on disk.

Each run is a LangGraph thread, stored in data/runs/checkpoints.db, so a run can
wait days for a person and survive restarts.
"""

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from taxagent.agent.llm import LLM, llm_from_env
from taxagent.agent.roster import load_roster
from taxagent.agent.workflow import build_workflow, sign_off_request
from taxagent.ingestion.manifest import new_run_id

RUNS_DIR = Path("data/runs")

MakeLLM = Callable[[dict[str, str]], LLM]  # roster -> LLM; tests pass a fake

# One answer at a time: "is the run still as you saw it?" and "then continue it"
# must happen with nothing in between
ANSWERING = threading.Lock()


class StaleAnswerError(ValueError):
    """The run changed after this person's page was drawn: the answer is out of date."""


def checkpointer() -> SqliteSaver:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RUNS_DIR / "checkpoints.db", check_same_thread=False)
    return SqliteSaver(conn)


def config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def record_of(values: dict) -> dict | None:
    """What the signer was shown and what they decided (None until a run is signed)."""
    if "sign_off" not in values:
        return None
    return {
        **sign_off_request(values),
        "reviewer": values.get("reviewer"),
        "sign_off": values["sign_off"],
    }


def fingerprint(checkpoint_id: str | None, pending: dict | None) -> str:
    # The request is included because a refused answer changes the request (it gains
    # the reasons) without creating a new checkpoint
    text = json.dumps([checkpoint_id, pending], sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def snapshot(workflow, run_id: str) -> dict:
    """The run's status, what it is waiting for (None when nothing), and its record.

    "version" is a fingerprint of where the run stands and what it is asking. It
    changes whenever either changes, so a page can tell whether the run is still
    the one it showed.
    """
    state = workflow.get_state(config(run_id))
    pending = next(
        (task.interrupts[0].value for task in state.tasks if task.interrupts), None
    )
    return {
        "run_id": run_id,
        "quarter": state.values.get("quarter"),
        "status": state.values.get("status"),
        "version": fingerprint(
            state.config["configurable"].get("checkpoint_id"), pending
        ),
        "pending": pending,
        "record": record_of(state.values),
        "trace": state.values.get("trace", []),
    }


def quarter_of(run_id: str, saver: SqliteSaver) -> str:
    # Reading saved state never runs a step, so no LLM is needed here
    values = build_workflow(None, saver).get_state(config(run_id)).values
    if not values:
        raise KeyError(f"No run called {run_id}")
    return values["quarter"]


# Every function below takes an optional `saver`. A long-lived program (the app)
# opens one and passes it in each time; a short one (the CLI) lets a new one be made.


def start_run(
    quarter: str, make_llm: MakeLLM = llm_from_env, saver: SqliteSaver | None = None
) -> dict:
    run_id = f"{quarter}-{new_run_id()}"
    saver = saver or checkpointer()
    workflow = build_workflow(make_llm(load_roster(quarter)), saver)
    workflow.invoke({"quarter": quarter}, config(run_id))
    return snapshot(workflow, run_id)


def run_status(run_id: str, saver: SqliteSaver | None = None) -> dict:
    saver = saver or checkpointer()
    quarter_of(run_id, saver)  # fails clearly for an unknown run
    return snapshot(build_workflow(None, saver), run_id)


def resume_run(
    run_id: str,
    answer: dict,
    make_llm: MakeLLM = llm_from_env,
    saver: SqliteSaver | None = None,
    expected: str | None = None,
) -> dict:
    """Continue a paused run with a person's answer.

    `expected` is the version the person was looking at. If the run has changed
    since, the answer is refused: it was written for a state that no longer exists.
    """
    saver = saver or checkpointer()
    quarter = quarter_of(run_id, saver)
    workflow = build_workflow(make_llm(load_roster(quarter)), saver)
    with ANSWERING:
        now = snapshot(workflow, run_id)
        if expected is not None and now["version"] != expected:
            raise StaleAnswerError(f"{run_id} changed after this answer was written")
        if now["pending"] is None:
            raise ValueError(f"{run_id} is not waiting for anyone")
        workflow.invoke(Command(resume=answer), config(run_id))
    return snapshot(workflow, run_id)


def list_runs(saver: SqliteSaver | None = None) -> list[dict]:
    """Every saved run with its status and what it waits for, newest first."""
    saver = saver or checkpointer()
    run_ids = {c.config["configurable"]["thread_id"] for c in saver.list(None)}
    workflow = build_workflow(None, saver)
    return [snapshot(workflow, run_id) for run_id in sorted(run_ids, reverse=True)]
