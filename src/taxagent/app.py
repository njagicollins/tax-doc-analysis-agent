"""The reviewer's app: a thin shell over runner.py.

Run it from the project root: uv run streamlit run src/taxagent/app.py
"""

import streamlit as st
from dotenv import load_dotenv

from taxagent.agent.runner import list_runs, resume_run, run_status, start_run
from taxagent.ingestion.raw_store import TamperedFileError
from taxagent.review.evidence import page_image, raw_file
from taxagent.schema.models import SourceRef

PEOPLE = ["alice", "bob", "carol"]  # stand-ins until there is a real login

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


def show_evidence(source: dict | None, quarter: str) -> None:
    """The page the value came from, so the reviewer checks against the source."""
    if source is None:
        st.warning("This run was saved before sources were recorded.")
        return
    ref = SourceRef(**source)
    if ref.page is None:
        st.info(f"Spreadsheet cell {ref.sheet}!{ref.cell}")
        return
    try:
        path = raw_file(ref, quarter)
    except (FileNotFoundError, TamperedFileError) as error:
        st.error(f"Can't show the evidence: {error}")
        return
    st.image(page_image(path, ref), caption=f"{path.name}, page {ref.page}")


def page_of(item: dict) -> tuple | None:
    source = item.get("source")
    return (source["file_sha256"], source["page"]) if source else None


def review_form(run: dict) -> None:
    request = run["pending"]
    for problem in request.get("problems", []):
        st.error(problem)

    # Values from the same page share one picture (E017's six boxes: one scan)
    pages: dict[tuple | None, list[dict]] = {}
    for item in request["items"]:
        pages.setdefault(page_of(item), []).append(item)

    with st.form(f"review-{run['run_id']}"):
        corrections = []
        for items in pages.values():
            evidence, values = st.columns(2)
            with evidence:
                show_evidence(items[0].get("source"), run["quarter"])
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


runs = {run["run_id"]: run for run in list_runs()}
if not runs:
    st.info("No runs yet. Start one from the sidebar.")
    st.stop()


def label(run_id: str) -> str:
    run = runs[run_id]
    waiting = run["pending"]["step"] if run["pending"] else "nobody"
    return f"{run_id}  ·  {run['status']}  ·  waiting for: {waiting}"


run_id = st.selectbox("Run", list(runs), format_func=label)
run = run_status(run_id)

st.metric("Status", run["status"])
if run["pending"] is None:
    st.success("Finished: not waiting for anyone.")
elif run["pending"]["step"] == "review":
    st.subheader("Review: type each value as it appears on the source")
    review_form(run)
else:
    st.subheader(f"Waiting for: {run['pending']['step']}")
    st.json(run["pending"])
