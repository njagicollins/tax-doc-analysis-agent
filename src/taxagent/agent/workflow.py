"""The quarterly run as a LangGraph workflow with two human checkpoints.

extract -> human_review -> compute -> explain -> summarize -> sign_off -> finalize

human_review and sign_off call interrupt(): the run pauses, its state is saved by
the checkpointer, and it resumes only when a person answers. The workflow cannot
reach finalize without a recorded human sign-off.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import TypeAdapter

from taxagent.agent.explain import ExplainedFinding, explain_finding
from taxagent.agent.llm import LLM
from taxagent.agent.summary import draft_summary
from taxagent.compute.findings import Finding, run_checks
from taxagent.compute.run import FINDING_JSON, load_values, previous_quarter
from taxagent.extraction.run import EXTRACTED_DIR, run_extraction
from taxagent.review.corrections import amount_problem, apply_corrections

RESULTS_DIR = Path("data/results")
EXPLAINED_JSON = TypeAdapter(ExplainedFinding)


class RunState(TypedDict, total=False):
    """Everything the run knows. Plain JSON-friendly data, so it can be saved."""

    quarter: str
    review_items: list[dict]
    reviewer: str
    corrections: list[dict]
    findings: list[dict]
    explained: list[dict]
    summary: dict
    sign_off: dict
    status: str


def review_problems(answer: dict, items: list[dict]) -> list[str]:
    """A review is complete only when every low-confidence value has a number."""
    if not answer.get("reviewer"):
        return ["reviewer name is required"]
    given = {
        (c.get("field"), c.get("employee_id")): c.get("value")
        for c in answer.get("corrections", [])
    }
    problems = []
    for item in items:
        value = given.get((item["field"], item["employee_id"]))
        problem = amount_problem(value)
        if problem:
            problems.append(f"{item['field']} ({item['employee_id']}) {problem}")
    return problems


def sign_off_problems(answer: dict, state: RunState) -> list[str]:
    signer = answer.get("signer")
    if not signer:
        return ["signer name is required"]
    problems = []
    if state.get("corrections") and signer == state.get("reviewer"):
        problems.append(
            f"maker-checker: {signer} corrected values in this run, "
            "so a different person must sign off"
        )
    decisions = answer.get("decisions", {})
    for item in state["findings"]:
        if decisions.get(item["id"]) not in ("accept", "reject"):
            problems.append(f"{item['id']} needs a decision: accept or reject")
    if not isinstance(answer.get("approve"), bool):
        problems.append("approve must be true or false")
    return problems


def ask_until_valid(request: dict, check) -> dict:
    """Pause for a human; if the answer is incomplete, ask again with the reasons."""
    while True:
        answer = interrupt(request)
        problems = check(answer)
        if not problems:
            return answer
        request = {**request, "problems": problems}


def build_workflow(llm: LLM, checkpointer: Any):
    def extract(state: RunState) -> RunState:
        result = run_extraction(state["quarter"])
        items = [
            {"field": v.field, "employee_id": v.employee_id, "confidence": v.confidence}
            for v in result.needs_review
        ]
        return {"review_items": items, "status": "extracted"}

    def human_review(state: RunState) -> RunState:
        items = state["review_items"]
        if not items:
            return {"corrections": [], "status": "reviewed"}
        answer = ask_until_valid(
            {"step": "review", "items": items},
            lambda answer: review_problems(answer, items),
        )
        corrections = [
            {**c, "value": str(Decimal(str(c["value"]))), "by": answer["reviewer"]}
            for c in answer["corrections"]
        ]
        return {
            "reviewer": answer["reviewer"],
            "corrections": corrections,
            "status": "reviewed",
        }

    def corrected_values(state: RunState):
        """This quarter's values with the reviewer's corrections applied."""
        quarter = state["quarter"]
        current = load_values(EXTRACTED_DIR / quarter / "values.jsonl")
        previous = load_values(
            EXTRACTED_DIR / previous_quarter(quarter) / "values.jsonl"
        )
        return apply_corrections(current, state.get("corrections", [])), previous

    def compute(state: RunState) -> RunState:
        current, previous = corrected_values(state)
        findings = run_checks(state["quarter"], current, previous)
        return {
            "findings": [
                {
                    "id": f"F{number}",
                    "finding": FINDING_JSON.dump_python(f, mode="json"),
                }
                for number, f in enumerate(findings, start=1)
            ],
            "status": "computed",
        }

    def explain(state: RunState) -> RunState:
        current, previous = corrected_values(state)
        explained = []
        for item in state["findings"]:
            finding: Finding = FINDING_JSON.validate_python(item["finding"])
            result = explain_finding(llm, finding, current, previous)
            explained.append(
                {
                    "finding_id": item["id"],
                    **EXPLAINED_JSON.dump_python(result, mode="json"),
                }
            )
        return {"explained": explained, "status": "explained"}

    def summarize(state: RunState) -> RunState:
        return {
            "summary": draft_summary(llm, state["quarter"], state["explained"]),
            "status": "summarized",
        }

    def sign_off(state: RunState) -> RunState:
        request = {
            "step": "sign_off",
            "summary": state["summary"],
            "findings": [
                {
                    "id": item["finding_id"],
                    "summary": item["finding"]["summary"],
                    "problems": item["problems"],
                }
                for item in state["explained"]
            ],
        }
        answer = ask_until_valid(
            request, lambda answer: sign_off_problems(answer, state)
        )
        return {
            "sign_off": {
                "signer": answer["signer"],
                "decisions": answer["decisions"],
                "approve": answer["approve"],
                "note": answer.get("note", ""),
            },
            "status": "approved" if answer["approve"] else "rejected",
        }

    def finalize(state: RunState, config: RunnableConfig) -> RunState:
        run_id = config["configurable"]["thread_id"]
        path = RESULTS_DIR / state["quarter"] / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"run_id": run_id, **state}, indent=2), encoding="utf-8"
        )
        return {}

    graph = StateGraph(RunState)
    graph.add_node("extract", extract)
    graph.add_node("human_review", human_review)
    graph.add_node("compute", compute)
    graph.add_node("explain", explain)
    graph.add_node("summarize", summarize)
    graph.add_node("sign_off", sign_off)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "human_review")
    graph.add_edge("human_review", "compute")
    graph.add_edge("compute", "explain")
    graph.add_edge("explain", "summarize")
    graph.add_edge("summarize", "sign_off")
    graph.add_edge("sign_off", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
