"""The whole pipeline as an ordered list of boxes, for the "How it works" picture.

The workflow's steps and their order come from LangGraph itself, so the picture
cannot disagree with the code. Only the boxes before and after the workflow are
written by hand, because getting the documents in runs as a separate command.

This module only says what the boxes are. How they look is the app's job.
"""

from taxagent.agent.workflow import build_workflow

# name -> (title, what it does, what it is built with)
BEFORE = {  # `taxagent ingest`, before the workflow starts
    "sources": (
        "Sources",
        "ADP documents and the payroll database",
        ["FastAPI (mock ADP)", "SQLite"],
    ),
    "ingest": (
        "Ingest",
        "Copy every file in and record its hash",
        ["httpx", "sqlite3", "SHA-256 hash"],
    ),
    "raw": (
        "Raw store",
        "Write-once copies: the evidence",
        ["files on disk", "JSON manifest"],
    ),
}
# Every workflow step. A new step with no entry here fails a test.
STEPS = {
    "extract": (
        "Extract",
        "Read each value and remember where it came from",
        ["PyMuPDF", "openpyxl", "csv", "Pydantic"],
    ),
    "human_review": (
        "Review",
        "A person types what the machine could not read",
        ["LangGraph interrupt", "Streamlit"],
    ),
    "compute": (
        "Compute",
        "Code does the checks and the math",
        ["plain Python", "Decimal"],
    ),
    "explain": (
        "Explain",
        "AI drafts an explanation for each finding",
        ["OpenAI API", "PII masking", "Pydantic"],
    ),
    "summarize": (
        "Summarize",
        "AI drafts the summary",
        ["OpenAI API", "PII masking", "Pydantic"],
    ),
    "sign_off": (
        "Sign-off",
        "A second person decides",
        ["LangGraph interrupt", "Streamlit"],
    ),
    "finalize": ("Finalize", "Save everything that was decided", ["JSON file"]),
}
AFTER = {
    "result": (
        "Saved result",
        "What the dashboard reads",
        ["JSON files", "Streamlit dashboard"],
    ),
}

HUMAN = {"human_review", "sign_off"}  # the run waits here for a person
AI = {"explain", "summarize"}  # the only steps where the AI writes
STORES = {"sources", "raw", "result"}  # data at rest

START, END = "__start__", "__end__"  # LangGraph's names for the two ends


def kind_of(name: str) -> str:
    if name in HUMAN:
        return "human"
    if name in AI:
        return "ai"
    return "store" if name in STORES else "code"


def workflow_order() -> list[str]:
    """The workflow's steps, each after the steps that lead to it, asked from LangGraph.

    Follows every arrow, so it still works if the workflow one day branches.
    """
    graph = build_workflow(None, None).get_graph()  # needs no LLM and no storage
    following: dict[str, list[str]] = {}
    for edge in graph.edges:
        following.setdefault(edge.source, []).append(edge.target)

    order, waiting = [], [START]
    while waiting:
        step = waiting.pop(0)
        for target in following.get(step, []):
            if target != END and target not in order:
                order.append(target)
                waiting.append(target)
    return order


def describe(name: str) -> dict:
    """One box: its words, its tools and its kind, looked up by name."""
    title, what, tools = {**BEFORE, **STEPS, **AFTER}[name]
    return {
        "name": name,
        "title": title,
        "what": what,
        "tools": tools,
        "kind": kind_of(name),
        "in_workflow": name in STEPS,
    }


def pipeline() -> list[dict]:
    """Every box from the sources to the saved result: the map, before any run."""
    return [describe(name) for name in [*BEFORE, *workflow_order(), *AFTER]]
