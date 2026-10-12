"""The quarterly run as a LangGraph workflow with two human checkpoints.

extract -> human_review -> compute -> explain -> summarize -> sign_off -> finalize

human_review and sign_off call interrupt(): the run pauses, its state is saved by
the checkpointer, and it resumes only when a person answers. The workflow cannot
reach finalize without a recorded human sign-off.
"""

import json
import operator
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import TypeAdapter

from taxagent.agent.explain import ExplainedFinding, explain_finding
from taxagent.agent.llm import LLM
from taxagent.agent.summary import draft_summary
from taxagent.agent.trace import traced
from taxagent.compute.findings import Finding, run_checks
from taxagent.compute.run import FINDING_JSON, load_values, previous_quarter
from taxagent.extraction.run import EXTRACTED_DIR, REVIEW_THRESHOLD, run_extraction
from taxagent.review.corrections import amount_problem, apply_corrections

RESULTS_DIR = Path("data/results")
EXPLAINED_JSON = TypeAdapter(ExplainedFinding)


class RunState(TypedDict, total=False):
    """Everything the run knows. Plain JSON-friendly data, so it can be saved."""

    quarter: str
    made_with: dict  # code version, prompts, models and settings behind this run
    review_items: list[dict]
    reviewer: str
    corrections: list[dict]
    findings: list[dict]
    explained: list[dict]
    summary: dict
    sign_off: dict
    status: str
    # One line per finished step. operator.add: each new line is added to the list
    trace: Annotated[list[dict], operator.add]


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


def sign_off_request(state: RunState) -> dict:
    """Everything the signer must see. Built from saved state, so it can be rebuilt
    later to show exactly what was signed."""
    reviewed = {
        (item["field"], item["employee_id"]): item for item in state["review_items"]
    }
    return {
        "step": "sign_off",
        "summary": state["summary"],
        # The checker must see what the maker typed, next to its source
        "corrections": [
            {
                **correction,
                "machine_value": reviewed[key].get("machine_value"),
                "source": reviewed[key].get("source"),
            }
            for correction in state.get("corrections", [])
            for key in [(correction["field"], correction["employee_id"])]
        ],
        "findings": [
            {
                "id": item["finding_id"],
                "summary": item["finding"]["summary"],
                "explanation": item["explanation"],
                "evidence": item["evidence"],
                "problems": item["problems"],
            }
            for item in state["explained"]
        ],
    }


def ask_until_valid(request: dict, check) -> tuple[dict, list[str]]:
    """Pause for a human; if the answer is incomplete, ask again with the reasons.

    Also returns every refusal, so the trace shows the answers that were sent back.
    """
    refused = []
    while True:
        answer = interrupt(request)
        problems = check(answer)
        if not problems:
            return answer, refused
        who = answer.get("reviewer") or answer.get("signer") or "Someone"
        refused.append(f"{who} answered and was asked again: {'; '.join(problems)}")
        request = {**request, "problems": problems}


def build_workflow(llm: LLM, checkpointer: Any):
    def extract(state: RunState) -> RunState:
        result = run_extraction(state["quarter"])
        items = [
            {
                "field": v.field,
                "employee_id": v.employee_id,
                "confidence": v.confidence,
                # What the machine read, if anything: shown to the signer only
                "machine_value": None if v.value is None else str(v.value),
                "source": v.source.model_dump(mode="json"),  # so a person can see it
            }
            for v in result.needs_review
        ]

        documents = {v.source.file_sha256 for v in result.values}
        decision = (
            f"{len(items)} values were read with less than {REVIEW_THRESHOLD:.0%} "
            "confidence, so the run pauses for a person"
            if items
            else "Every value was read with enough confidence, so no person is needed"
        )
        return {
            "review_items": items,
            "status": "extracted",
            "did": f"Read {len(result.values)} values from {len(documents)} documents",
            "notes": [decision],
        }

    def human_review(state: RunState) -> RunState:
        items = state["review_items"]
        if not items:
            return {
                "corrections": [],
                "status": "reviewed",
                "did": "Skipped: nothing needed a person",
            }
        answer, refused = ask_until_valid(
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
            "did": f"{answer['reviewer']} typed {len(corrections)} values from the source",
            "notes": refused,
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
            "did": f"Ran the checks and found {len(findings)} things for a person to judge",
            "notes": [
                f"F{number}: {f.summary}" for number, f in enumerate(findings, start=1)
            ],
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
        notes = []
        for item in explained:
            if item["explanation"] and not item["explanation"]["can_determine_cause"]:
                notes.append(
                    f"{item['finding_id']}: the AI said it could not tell the cause"
                )
            notes += [
                f"{item['finding_id']}: a check on the AI's text failed: {problem}"
                for problem in item["problems"]
            ]
        return {
            "explained": explained,
            "status": "explained",
            "did": f"{llm.models['large']} drafted {len(explained)} explanations",
            "notes": notes,
        }

    def summarize(state: RunState) -> RunState:
        summary = draft_summary(llm, state["quarter"], state["explained"])
        sentences = len(summary["claims"])
        return {
            "summary": summary,
            "status": "summarized",
            "did": f"{llm.models['large']} drafted a {sentences}-sentence summary",
            "notes": [
                f"A check on the AI's text failed: {problem}"
                for problem in summary["problems"]
            ],
        }

    def sign_off(state: RunState) -> RunState:
        request = sign_off_request(state)
        answer, refused = ask_until_valid(
            request, lambda answer: sign_off_problems(answer, state)
        )
        verdict = "approved" if answer["approve"] else "rejected"
        decisions = [f"{name}: {word}" for name, word in answer["decisions"].items()]
        return {
            "did": f"{answer['signer']} {verdict} the run",
            "notes": refused + decisions,
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
        return {"did": f"Saved the result to {path.as_posix()}"}

    steps = {
        "extract": extract,
        "human_review": human_review,
        "compute": compute,
        "explain": explain,
        "summarize": summarize,
        "sign_off": sign_off,
        "finalize": finalize,
    }
    graph = StateGraph(RunState)
    for name, node in steps.items():
        graph.add_node(name, traced(name, node))  # every step leaves a trace line

    graph.add_edge(START, "extract")
    graph.add_edge("extract", "human_review")
    graph.add_edge("human_review", "compute")
    graph.add_edge("compute", "explain")
    graph.add_edge("explain", "summarize")
    graph.add_edge("summarize", "sign_off")
    graph.add_edge("sign_off", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)
