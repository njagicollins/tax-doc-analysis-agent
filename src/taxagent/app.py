"""The reviewer's app: a thin shell over runner.py and review/dashboard.py.

Run it from the project root: uv run streamlit run src/taxagent/app.py
"""

from html import escape
from itertools import groupby

import streamlit as st
from dotenv import load_dotenv

from taxagent.agent.diagram import HUMAN, describe, pipeline, workflow_order
from taxagent.agent.runner import (
    StaleAnswerError,
    checkpointer,
    list_runs,
    resume_run,
    run_status,
    start_run,
)
from taxagent.agent.trace import duration, ingest_line, with_waits
from taxagent.ingestion.manifest import read_rows
from taxagent.ingestion.raw_store import TamperedFileError
from taxagent.review.dashboard import (
    check_status,
    counts_by_category,
    load_results,
    official,
    rejected_since,
)
from taxagent.review.evidence import location, page_image, raw_file
from taxagent.schema.models import SourceRef

PEOPLE = ["alice", "bob", "carol"]  # stand-ins until there is a real login

# One colour per meaning, used everywhere: green = good, red = bad, orange = waiting
COLOUR = {
    "approved": "green",
    "approve": "green",
    "accept": "green",
    "pass": "green",
    "rejected": "red",
    "reject": "red",
    "fail": "red",
}
BAR = "#3987E5"  # one blue for every bar: red and green already mean bad and good
DOT = {"green": "🟢", "red": "🔴", "orange": "🟠"}


def colour_of(word: str) -> str:
    return COLOUR.get(word, "orange")


def coloured(word: str) -> str:
    """The word in its colour, in the markdown Streamlit understands."""
    return f":{colour_of(word)}[**{word}**]"


load_dotenv()
st.set_page_config(page_title="Tax document analysis", layout="wide")
st.title("Tax document analysis")


@st.cache_resource
def saver():
    """One database connection for as long as the app runs, shared by every click.

    Without the cache, each rerun of this script would open another connection
    and never close it.
    """
    return checkpointer()


def answer(run: dict, reply: dict, doing: str) -> None:
    """Send a person's answer, unless the run changed after their page was drawn."""
    seen = st.session_state.setdefault("seen", {})
    try:
        with st.spinner(doing):
            resume_run(
                run["run_id"],
                reply,
                saver=saver(),
                expected=seen.get(run["run_id"], run["version"]),
            )
    except StaleAnswerError:
        st.error(
            "Your answer was not used: this run changed after you opened it, because "
            "someone else answered first. Check what the page shows now, then answer "
            "again if it still applies."
        )
        return
    st.session_state["answered"] = True  # the change we are about to see is our own
    st.rerun()


with st.sidebar:
    user = st.selectbox("You are", PEOPLE)
    st.caption("Simulated login. In production this comes from Entra ID.")
    st.divider()
    quarter = st.text_input("Quarter", "2026Q2")
    if st.button("Start a run"):
        with st.spinner("Extracting..."):
            started = start_run(quarter, saver=saver())
        st.success(f"Started {started['run_id']}")


def show_evidence(source: dict | None) -> None:
    """The page the value came from, so the reviewer checks against the source."""
    if source is None:
        st.warning("This run was saved before sources were recorded.")
        return
    ref = SourceRef(**source)
    if ref.page is None:
        st.info(f"Spreadsheet cell {ref.sheet}!{ref.cell}")
        return
    try:
        path = raw_file(ref)
    except (FileNotFoundError, TamperedFileError) as error:
        st.error(f"Can't show the evidence: {error}")
        return
    st.image(page_image(path, ref), caption=f"{path.name}, page {ref.page}")


def page_of(item: dict) -> tuple | None:
    source = item.get("source")
    return (source["file_sha256"], source["page"]) if source else None


def by_page(items: list[dict]) -> list[list[dict]]:
    """Values from the same page share one picture (E017's six boxes: one scan)."""
    pages: dict[tuple | None, list[dict]] = {}
    for item in items:
        pages.setdefault(page_of(item), []).append(item)
    return list(pages.values())


def review_form(run: dict) -> None:
    request = run["pending"]
    for problem in request.get("problems", []):
        st.error(problem)

    with st.form(f"review-{run['run_id']}"):
        corrections = []
        for items in by_page(request["items"]):
            evidence, values = st.columns(2)
            with evidence:
                show_evidence(items[0].get("source"))
            with values:
                for item in items:
                    value = st.text_input(
                        f"{item['field']} ({item['employee_id']}), "
                        f"read with confidence {item['confidence']:.0%}",
                        key=f"{run['run_id']}-{item['field']}-{item['employee_id']}",
                    )
                    corrections.append(
                        {
                            "field": item["field"],
                            "employee_id": item["employee_id"],
                            "value": value.strip(),
                        }
                    )
        submitted = st.form_submit_button(f"Submit review as {user}")

    if submitted:
        answer(
            run,
            {"reviewer": user, "corrections": corrections},
            "Checking your values, then computing and explaining...",
        )


def evidence_table(evidence: list[dict]) -> list[dict]:
    rows = []
    for item in evidence:
        try:
            where = "; ".join(location(SourceRef(**s)) for s in item["sources"])
        except (FileNotFoundError, TamperedFileError) as error:
            where = f"can't verify: {error}"
        rows.append(
            {
                "id": item["id"],
                "what": item["label"],
                "value": item["value"],
                "where": where,
            }
        )
    return rows


def show_corrections(corrections: list[dict]) -> None:
    """What the reviewer typed, beside the page it was typed from."""
    if not corrections:
        return
    typed_by = corrections[0]["by"]
    st.markdown(f"**Values typed in by {typed_by}**: check each against its page")
    for items in by_page(corrections):
        evidence, values = st.columns(2)
        with evidence:
            show_evidence(items[0].get("source"))
        with values:
            st.dataframe(
                [
                    {
                        "field": item["field"],
                        "employee": item["employee_id"],
                        "typed": item["value"],
                        "machine read": item.get("machine_value") or "could not read",
                        "typed by": item["by"],
                    }
                    for item in items
                ],
                hide_index=True,
            )


def show_summary(request: dict) -> None:
    st.markdown("**Summary** (drafted by AI, every sentence cites a finding)")
    for claim in request["summary"]["claims"]:
        st.markdown(f"- {claim['text']}")
    for problem in request["summary"]["problems"]:
        st.warning(f"Summary check failed: {problem}")


def show_finding(finding: dict, fold_evidence: bool = True) -> None:
    st.markdown(f"#### {finding['id']}: {finding['summary']}")
    for problem in finding["problems"]:
        st.warning(f"Explanation check failed: {problem}")
    explanation = finding.get("explanation")
    if explanation:
        st.markdown("AI explanation (a draft, not a decision):")
        for claim in explanation["claims"]:
            cited = ", ".join(claim["evidence_ids"])
            st.markdown(f"- {claim['text']} *[{cited}]*")
        if not explanation["can_determine_cause"]:
            st.info("The AI could not tell the cause from the evidence.")
    if finding.get("evidence"):
        table = evidence_table(finding["evidence"])
        if fold_evidence:
            with st.expander("Evidence"):
                st.dataframe(table, hide_index=True)
        else:  # already inside an expander, and Streamlit can't put one in another
            st.caption("Evidence")
            st.dataframe(table, hide_index=True)


def sign_off_form(run: dict) -> None:
    request = run["pending"]
    for problem in request.get("problems", []):
        st.error(problem)

    show_corrections(request.get("corrections", []))
    show_summary(request)

    with st.form(f"sign-off-{run['run_id']}"):
        decisions = {}
        for finding in request["findings"]:
            show_finding(finding)
            decisions[finding["id"]] = st.radio(
                f"Your decision on {finding['id']}",
                ["accept", "reject"],
                format_func=coloured,  # what is shown; the saved answer stays plain
                captions=[
                    "It is real and the evidence supports the explanation",
                    "The finding or its explanation is wrong",
                ],
                index=None,  # no default: every finding needs a conscious choice
                horizontal=True,
                key=f"{run['run_id']}-{finding['id']}",
            )
        st.divider()
        st.caption("Accepting a finding says it is real. It does not approve the run.")
        verdict = st.radio(
            "The run as a whole",
            ["approve", "reject"],
            format_func=coloured,
            captions=[
                "The numbers can be used as they stand",
                "Something must be fixed first",
            ],
            index=None,
            horizontal=True,
            key=f"{run['run_id']}-verdict",
        )
        note = st.text_area("Note", key=f"{run['run_id']}-note")
        submitted = st.form_submit_button(f"Sign off as {user}")

    if submitted:
        reply = {
            "signer": user,
            "decisions": {k: v for k, v in decisions.items() if v is not None},
            "approve": None if verdict is None else verdict == "approve",
            "note": note,
        }
        answer(run, reply, "Recording your sign-off...")


def show_record(run: dict) -> None:
    """A finished run, read-only: what the signer saw and what they decided."""
    record = run["record"]
    if record is None:
        st.warning("This run stopped before anyone signed it off.")
        return
    signed = record["sign_off"]
    if signed["approve"]:
        st.success(f"Approved by {signed['signer']}")
    else:
        st.error(f"Rejected by {signed['signer']}")
    if signed.get("note"):
        st.markdown(f"**Signer's note:** {signed['note']}")

    for finding in record["findings"]:
        decision = signed["decisions"][finding["id"]]
        with st.container(border=True):
            st.markdown(f"**{finding['id']}**: {finding['summary']}")
            st.badge(decision, color=colour_of(decision))

    with st.expander("What the signer saw: typed values, AI drafts and evidence"):
        show_corrections(record["corrections"])
        show_summary(record)
        for finding in record["findings"]:
            show_finding(finding, fold_evidence=False)


def runs_page() -> None:
    runs = {run["run_id"]: run for run in list_runs(saver())}
    if not runs:
        st.info("No runs yet. Start one from the sidebar.")
        return

    def label(run_id: str) -> str:
        run = runs[run_id]
        waiting = run["pending"]["step"] if run["pending"] else "nobody"
        dot = DOT[colour_of(run["status"])]
        return f"{dot} {run_id}  ·  {run['status']}  ·  waiting for: {waiting}"

    run_id = st.selectbox("Run", list(runs), format_func=label)
    run = run_status(run_id, saver())

    # Has this run changed since this person last saw it, and not by their own answer?
    seen = st.session_state.setdefault("seen", {})
    own_answer = st.session_state.pop("answered", False)
    if seen.get(run_id) not in (None, run["version"]) and not own_answer:
        st.warning(
            "This run changed since you last looked: someone else answered it. "
            "The page now shows where it stands."
        )

    st.badge(run["status"], color=colour_of(run["status"]))
    if run["pending"] is None:
        st.subheader("Record: what was signed, and the decisions")
        show_record(run)
    elif run["pending"]["step"] == "review":
        st.subheader("Review: type each value as it appears on the source")
        review_form(run)
    elif run["pending"]["step"] == "sign_off":
        st.subheader("Sign-off: decide on each finding, then on the run")
        sign_off_form(run)
    else:
        st.subheader(f"Waiting for: {run['pending']['step']}")
        st.json(run["pending"])
    seen[run_id] = run["version"]  # what this person has now been shown


def bars_html(counts: dict[str, int]) -> str:
    """A bar per category, biggest first, with its full name and its number."""
    longest = max(counts.values())
    rows = sorted(counts.items(), key=lambda pair: -pair[1])
    return "".join(
        f"""
<div style="display:grid;grid-template-columns:minmax(180px,38%) 1fr 36px;gap:12px;
            align-items:center;margin:10px 0;color:#E8EEF4">
  <div>{escape(name)}</div>
  <div style="background:#1B2A3C;border-radius:4px">
    <div style="width:{count / longest:.0%};height:18px;border-radius:4px;
                background:{BAR}"></div>
  </div>
  <div style="text-align:right;font-weight:700">{count}</div>
</div>"""
        for name, count in rows
    )


def dashboard_page() -> None:
    results = load_results()
    quarters = official(results)
    if not quarters:
        st.info("Nothing to show yet: no run has been approved.")
        return

    quarter = st.selectbox("Quarter", sorted(quarters, reverse=True))
    result = quarters[quarter]
    signer = result["sign_off"]["signer"]
    st.caption(
        f"The latest approved run: {result['run_id']}, approved by {signer}. "
        "Rejected and unfinished runs are not counted."
    )
    later = rejected_since(results, result)
    if later:
        st.warning(
            f"{len(later)} later run(s) for {quarter} were rejected. "
            "These numbers may be out of date: open the rejected run to see why."
        )

    checks = check_status(result)
    counts = counts_by_category(result)
    passed = sum(row["result"] == "pass" for row in checks)
    tiles = st.columns(3)
    tiles[0].metric("Checks passed", f"{passed} of {len(checks)}")
    tiles[1].metric("Findings", len(result["findings"]))
    tiles[2].metric("Values typed in by a person", len(result.get("corrections", [])))

    left, right = st.columns(2)
    with left:
        st.subheader("Checks")
        for row in checks:
            found = f" ({row['findings']} found)" if row["findings"] else ""
            st.markdown(
                f":{colour_of(row['result'])}-badge[{row['result']}] {row['check']}{found}"
            )
    with right:
        st.subheader("What needed a person, by category")
        if counts:
            st.html(bars_html(counts))
        else:
            st.success("Nothing needed a person this quarter.")

    st.subheader("Findings and decisions")
    decisions = result["sign_off"]["decisions"]
    for item in result["findings"]:
        decision = decisions[item["id"]]
        with st.container(border=True):
            st.markdown(f"**{item['id']}**: {item['finding']['summary']}")
            st.badge(decision, color=colour_of(decision))


# The "How it works" tab. kind -> (colour, what it means)
KIND = {
    "human": ("#F59E0B", "waits for a person"),
    "ai": ("#9085E9", "AI drafts text"),
    "code": ("#5B7083", "code, no AI"),
    "store": ("#2DD4BF", "stored data"),
}
MUTED = "#C5D0DB"
ARROW = '<div style="text-align:center;color:#5B7083;font-size:20px;line-height:30px">↓</div>'
CHIP = (
    "border:1px solid #3A4C60;border-radius:999px;padding:1px 10px;"
    f"font-size:13px;color:{MUTED}"
)
FOOT = "margin-top:10px;padding-top:8px;border-top:1px solid #2C3E50"
WAITING_NOW = (
    f'<div style="{FOOT};color:#F59E0B;font-weight:600">Waiting now for a person</div>'
)
NOT_REACHED = f'<div style="{FOOT};color:{MUTED}">Not reached yet</div>'
NOT_TRACED = (
    f'<div style="{FOOT};color:{MUTED}">Ran before tracing was added: no details</div>'
)
# What a paused run says it waits for -> the workflow step that asked
ASKED_BY = {"review": "human_review", "sign_off": "sign_off"}


def box_html(number: int, box: dict, foot: str = "", faded: bool = False) -> str:
    """One step as a card: number and name, what it does, what it is built with.

    `foot` is what happened at this step in one run; empty on the plain map.
    """
    colour, meaning = KIND[box["kind"]]
    chips = "".join(
        f'<span style="{CHIP}">{escape(tool)}</span>' for tool in box["tools"]
    )
    return f"""
<div style="background:#1B2A3C;border:1px solid #2C3E50;border-left:6px solid {colour};
            border-radius:10px;padding:12px 16px;color:#E8EEF4;
            opacity:{0.5 if faded else 1}">
  <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px">
    <div style="flex:1;min-width:260px">
      <div style="font-weight:700;font-size:17px">{number}. {escape(box["title"])}</div>
      <div style="color:{MUTED}">{escape(box["what"])}</div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">{chips}</div>
    </div>
    <div style="font-size:13px;color:{MUTED};white-space:nowrap">
      <span style="color:{colour}">●</span> {meaning}
    </div>
  </div>{foot}
</div>"""


def trace_html(line: dict) -> str:
    """What one step did in this run: how long, what, and the decisions it made."""
    if line["waited"] is None:
        took = f"took {duration(line['seconds'])}"
    else:
        took = f"waited {duration(line['waited'])} for a person"
    notes = "".join(f"<li>{escape(note)}</li>" for note in line.get("notes", []))
    return f"""
  <div style="{FOOT}">
    <span style="{CHIP};color:#E8EEF4;border-color:#2DD4BF">{took}</span>
    <span style="margin-left:8px">{escape(line["did"])}</span>
    <ul style="margin:6px 0 0 0;padding-left:22px;color:{MUTED}">{notes}</ul>
  </div>"""


def show_cards(cards: list[str]) -> None:
    st.html(f'<div style="max-width:820px">{ARROW.join(cards)}</div>')


def show_map() -> None:
    """Every step, before any run: what exists and what it is built with."""
    st.caption(
        "The workflow steps and their order are read from the code itself, "
        "so this map is always current."
    )
    parts = []
    numbered = enumerate(pipeline(), start=1)
    for inside, group in groupby(numbered, key=lambda pair: pair[1]["in_workflow"]):
        cards = ARROW.join(box_html(number, box) for number, box in group)
        if inside:  # frame the steps LangGraph runs, and say what the frame means
            cards = f"""
<div style="border:1px dashed #5B7083;border-radius:14px;padding:14px">
  <div style="font-size:13px;color:{MUTED};margin-bottom:10px">
    <b style="color:#E8EEF4">THE WORKFLOW</b> · LangGraph saves the run to SQLite
    after every step, so it can wait days for a person and survive a restart
  </div>{cards}
</div>"""
        parts.append(cards)
    show_cards(parts)


def show_trace(run: dict) -> None:
    """One run, step by step in the order things happened, then what is still to come."""
    lines = run["trace"]
    if not lines:
        st.info(
            "This run was saved before tracing was added. "
            "Start a new run to see its trace."
        )
        return
    done = with_waits(lines, HUMAN)  # waits are measured between this run's own steps
    waiting = ASKED_BY.get(run["pending"]["step"]) if run["pending"] else None
    # A run started before tracing existed has early steps with no line
    order = workflow_order()
    missing = [step for step in order if step not in done and step != waiting]
    first_traced = order.index(lines[0]["step"])
    untraced = [step for step in missing if order.index(step) < first_traced]
    later = [step for step in missing if step not in untraced]
    # Ingest is a separate command that ran earlier: shown first, never counted as a wait
    ingest = ingest_line(run["quarter"], read_rows(), before=lines[0]["finished_at"])
    timed = [*([{**ingest, "waited": None}] if ingest else []), *done.values()]

    tiles = st.columns(3)
    tiles[0].metric("Steps finished", len(timed) + len(untraced))
    tiles[1].metric("Machine time", duration(sum(line["seconds"] for line in timed)))
    tiles[2].metric(
        "Waiting for people", duration(sum(line["waited"] or 0 for line in timed))
    )

    # (step, what to say under it, faded?) from first to last
    rows = [
        (line["step"], trace_html(line), False)
        for line in timed[: len(timed) - len(done)]
    ]
    rows += [(step, NOT_TRACED, True) for step in untraced]
    rows += [(step, trace_html(line), False) for step, line in done.items()]
    if waiting:
        rows.append((waiting, WAITING_NOW, False))
    rows += [(step, NOT_REACHED, True) for step in later]
    show_cards(
        [
            box_html(number, describe(step), foot, faded)
            for number, (step, foot, faded) in enumerate(rows, start=1)
        ]
    )


def how_it_works_page() -> None:
    runs = {run["run_id"]: run for run in list_runs(saver())}
    chosen = st.selectbox(
        "Follow a run",
        [None, *runs],
        index=1 if runs else 0,  # the newest run, when there is one
        format_func=lambda run_id: run_id or "No run: show the map of every step",
    )
    if chosen is None:
        show_map()
    else:
        show_trace(runs[chosen])


runs_tab, dashboard_tab, how_tab = st.tabs(["Runs", "Dashboard", "How it works"])
with runs_tab:
    runs_page()
with dashboard_tab:
    dashboard_page()
with how_tab:
    how_it_works_page()
