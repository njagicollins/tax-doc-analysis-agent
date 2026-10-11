"""The reviewer's app: a thin shell over runner.py.

Run it from the project root: uv run streamlit run src/taxagent/app.py
"""

import streamlit as st
from dotenv import load_dotenv

from taxagent.agent.runner import list_runs, resume_run, run_status, start_run
from taxagent.ingestion.raw_store import TamperedFileError
from taxagent.review.evidence import location, page_image, raw_file
from taxagent.schema.models import SourceRef

PEOPLE = ["alice", "bob", "carol"]  # stand-ins until there is a real login

# One colour per meaning, used everywhere: green = good, red = bad, orange = waiting
COLOUR = {"approved": "green", "accept": "green", "rejected": "red", "reject": "red"}
DOT = {"green": "🟢", "red": "🔴", "orange": "🟠"}


def colour_of(word: str) -> str:
    return COLOUR.get(word, "orange")


load_dotenv()
st.set_page_config(page_title="Tax document analysis", layout="wide")
st.title("Tax document analysis")

with st.sidebar:
    user = st.selectbox("You are", PEOPLE)
    st.caption("Simulated login. In production this comes from Entra ID.")
    st.divider()
    quarter = st.text_input("Quarter", "2026Q2")
    if st.button("Start a run"):
        with st.spinner("Extracting..."):
            started = start_run(quarter)
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
        with st.spinner("Checking your values, then computing and explaining..."):
            resume_run(run["run_id"], {"reviewer": user, "corrections": corrections})
        st.rerun()


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
        answer = {
            "signer": user,
            "decisions": {k: v for k, v in decisions.items() if v is not None},
            "approve": None if verdict is None else verdict == "approve",
            "note": note,
        }
        with st.spinner("Recording your sign-off..."):
            resume_run(run["run_id"], answer)
        st.rerun()


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


runs = {run["run_id"]: run for run in list_runs()}
if not runs:
    st.info("No runs yet. Start one from the sidebar.")
    st.stop()


def label(run_id: str) -> str:
    run = runs[run_id]
    waiting = run["pending"]["step"] if run["pending"] else "nobody"
    dot = DOT[colour_of(run["status"])]
    return f"{dot} {run_id}  ·  {run['status']}  ·  waiting for: {waiting}"


run_id = st.selectbox("Run", list(runs), format_func=label)
run = run_status(run_id)

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
