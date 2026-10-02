"""Start, inspect and resume workflow runs that are saved on disk.

Each run is a LangGraph thread, stored in data/runs/checkpoints.db, so a run can
wait days for a person and survive restarts.
"""

import sqlite3
from collections.abc import Callable
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from taxagent.agent.llm import LLM, llm_from_env
from taxagent.agent.roster import load_roster
from taxagent.agent.workflow import build_workflow
from taxagent.ingestion.manifest import new_run_id

RUNS_DIR = Path("data/runs")

MakeLLM = Callable[[dict[str, str]], LLM]  # roster -> LLM; tests pass a fake


def checkpointer() -> SqliteSaver:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(RUNS_DIR / "checkpoints.db", check_same_thread=False)
    return SqliteSaver(conn)


def config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


def snapshot(workflow, run_id: str) -> dict:
    """The run's status, and what it is waiting for (None when nothing)."""
    state = workflow.get_state(config(run_id))
    pending = next(
        (task.interrupts[0].value for task in state.tasks if task.interrupts), None
    )
    return {"run_id": run_id, "status": state.values.get("status"), "pending": pending}


def quarter_of(run_id: str, saver: SqliteSaver) -> str:
    # Reading saved state never runs a step, so no LLM is needed here
    values = build_workflow(None, saver).get_state(config(run_id)).values
    if not values:
        raise KeyError(f"No run called {run_id}")
    return values["quarter"]


def start_run(quarter: str, make_llm: MakeLLM = llm_from_env) -> dict:
    run_id = f"{quarter}-{new_run_id()}"
    workflow = build_workflow(make_llm(load_roster(quarter)), checkpointer())
    workflow.invoke({"quarter": quarter}, config(run_id))
    return snapshot(workflow, run_id)


def run_status(run_id: str) -> dict:
    saver = checkpointer()
    quarter_of(run_id, saver)  # fails clearly for an unknown run
    return snapshot(build_workflow(None, saver), run_id)


def resume_run(run_id: str, answer: dict, make_llm: MakeLLM = llm_from_env) -> dict:
    saver = checkpointer()
    quarter = quarter_of(run_id, saver)
    workflow = build_workflow(make_llm(load_roster(quarter)), saver)
    if snapshot(workflow, run_id)["pending"] is None:
        raise ValueError(f"{run_id} is not waiting for anyone")
    workflow.invoke(Command(resume=answer), config(run_id))
    return snapshot(workflow, run_id)
