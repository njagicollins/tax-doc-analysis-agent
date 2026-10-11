"""A picture of the whole pipeline, drawn from the real workflow.

The steps and arrows of the workflow come from LangGraph itself, so the picture
cannot disagree with the code. Only the part before the workflow (getting the
documents in) is written by hand, because it runs as a separate command.

The result is DOT, the text format Graphviz draws: `a -> b` is an arrow.
"""

from itertools import pairwise

from taxagent.agent.workflow import build_workflow

# Before the workflow starts: `taxagent ingest`
BEFORE = {
    "sources": "Sources\nADP documents, payroll database",
    "ingest": "Ingest\ncopy every file in, record its hash",
    "raw": "Raw store\nwrite-once: the evidence",
}
AFTER = {"result": "Saved result\nthe dashboard reads this"}
STORES = {"sources", "raw", "result"}  # data at rest, drawn as cylinders

# Every workflow step, in words. A new step with no words here fails a test.
STEPS = {
    "extract": "Extract\nread each value, remember where it came from",
    "human_review": "Review\na person types what the machine could not read",
    "compute": "Compute\ncode does the checks and the math",
    "explain": "Explain\nAI drafts an explanation for each finding",
    "summarize": "Summarize\nAI drafts the summary",
    "sign_off": "Sign-off\na second person decides",
    "finalize": "Finalize\nsave everything that was decided",
}
HUMAN = {"human_review", "sign_off"}  # the run waits here for a person
AI = {"explain", "summarize"}  # the only steps where the AI writes

START, END = "__start__", "__end__"  # LangGraph's names for the two ends

INK = "#E8EEF4"
LOOK = {
    "human": f'fillcolor="#F59E0B" fontcolor="#1B2A38" color="{INK}"',
    "ai": f'fillcolor="#9085E9" fontcolor="#1B2A38" color="{INK}"',
    "code": f'fillcolor="#1B2A3C" fontcolor="{INK}" color="#5B7083"',
    "store": f'shape=cylinder fillcolor="#0F1B2A" fontcolor="{INK}" color="#2DD4BF"',
}


def kind_of(name: str) -> str:
    if name in HUMAN:
        return "human"
    if name in AI:
        return "ai"
    return "store" if name in STORES else "code"


def workflow_steps() -> tuple[list[str], list[tuple[str, str]]]:
    """The workflow's steps and arrows, asked from LangGraph."""
    graph = build_workflow(None, None).get_graph()  # drawing needs no LLM, no storage
    steps = [name for name in graph.nodes if name not in (START, END)]
    arrows = [(edge.source, edge.target) for edge in graph.edges]
    return steps, arrows


def pipeline_dot() -> str:
    steps, arrows = workflow_steps()
    labels = {**BEFORE, **{step: STEPS[step] for step in steps}, **AFTER}
    # The workflow begins at the raw store and ends in the saved result
    ends = {START: "raw", END: "result"}
    arrows = list(pairwise(BEFORE)) + [
        (ends.get(source, source), ends.get(target, target))
        for source, target in arrows
    ]

    lines = [
        "digraph pipeline {",
        '  bgcolor="transparent"',
        '  node [shape=box style="rounded,filled" fontname="Helvetica" fontsize=12]',
        f'  edge [color="{INK}"]',
    ]
    for name, label in labels.items():
        text = label.replace("\n", "\\n")
        lines.append(f'  {name} [label="{text}" {LOOK[kind_of(name)]}]')
    lines += [f"  {source} -> {target}" for source, target in arrows]
    return "\n".join([*lines, "}"])
