import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from synthetic.__main__ import main as generate_everything
from taxagent.agent import runner
from taxagent.agent import workflow as workflow_module
from taxagent.agent.explain import Claim, Explanation
from taxagent.agent.roster import load_roster
from taxagent.agent.runner import (
    StaleAnswerError,
    checkpointer,
    list_runs,
    resume_run,
    run_status,
    start_run,
)
from taxagent.agent.summary import Summary
from taxagent.agent.workflow import build_workflow
from taxagent.audit.log import read_entries, verify
from taxagent.extraction.run import run_extraction
from taxagent.ingestion.pipeline import ingest
from taxagent.ingestion.sources import SqlPayrollSource
from taxagent.review.evidence import raw_file
from taxagent.schema.models import SourceRef

E017_BOXES = [f"w2.box_{n}" for n in range(1, 7)]


class FolderSource:
    name = "adp"

    def __init__(self, folder):
        self.folder = folder

    def fetch_documents(self, quarter):
        return [
            (path.name, path.read_bytes())
            for path in sorted(self.folder.iterdir())
            if quarter in path.name or "w2_" in path.name
        ]


class FakeLLM:
    """Answers with the right shape for each question; no network, no cost."""

    def __init__(self):
        self.roster = {"E007": "Patrick Sanchez"}
        self.models = {"small": "tiny-model", "large": "big-model"}

    def parse(self, role, instructions, prompt, schema):
        if schema is Explanation:
            return Explanation(
                claims=[Claim(text="See the evidence.", evidence_ids=["EV1"])],
                can_determine_cause=False,
            )
        return Summary(claims=[Claim(text="Two findings.", evidence_ids=["F1", "F2"])])


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A generated, ingested world with Q1 already extracted, inside tmp_path."""
    monkeypatch.chdir(tmp_path)
    generate_everything()
    sources = [
        FolderSource(Path("data/sources/adp")),
        SqlPayrollSource(Path("data/sources/sql/payroll.db")),
    ]
    for quarter in ["2026Q1", "2026Q2"]:
        ingest(quarter, sources)
    run_extraction("2026Q1")
    return tmp_path


def open_workflow(path):
    conn = sqlite3.connect(path / "checkpoints.db", check_same_thread=False)
    return build_workflow(FakeLLM(), SqliteSaver(conn))


RUN = {"configurable": {"thread_id": "2026Q2-test"}}


def full_review(reviewer="alice"):
    corrections = [
        {"field": box, "employee_id": "E017", "value": "1000.00"} for box in E017_BOXES
    ]
    return {"reviewer": reviewer, "corrections": corrections}


def sign_off(signer, approve=True):
    return {
        "signer": signer,
        "decisions": {"F1": "accept", "F2": "accept"},
        "approve": approve,
    }


def pending(workflow):
    return workflow.get_state(RUN).tasks[0].interrupts[0].value


def test_run_pauses_for_review_of_the_unreadable_w2(world):
    workflow = open_workflow(world)

    workflow.invoke({"quarter": "2026Q2"}, RUN)

    request = pending(workflow)
    assert request["step"] == "review"
    assert {(i["field"], i["employee_id"]) for i in request["items"]} == {
        (box, "E017") for box in E017_BOXES
    }


def test_an_incomplete_review_is_asked_again(world):
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)

    workflow.invoke(Command(resume={"reviewer": "alice", "corrections": []}), RUN)

    request = pending(workflow)
    assert request["step"] == "review"
    assert len(request["problems"]) == 6


def test_full_run_reaches_sign_off_with_both_findings(world):
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)

    workflow.invoke(Command(resume=full_review()), RUN)

    request = pending(workflow)
    assert request["step"] == "sign_off"
    assert [f["id"] for f in request["findings"]] == ["F1", "F2"]
    assert request["summary"]["problems"] == []


def test_maker_checker_blocks_the_reviewer_from_signing_off(world):
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)
    workflow.invoke(Command(resume=full_review("alice")), RUN)

    workflow.invoke(Command(resume=sign_off("alice")), RUN)

    [problem] = pending(workflow)["problems"]
    assert problem.startswith("maker-checker: alice")


def test_a_different_signer_finalizes_the_run(world):
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)
    workflow.invoke(Command(resume=full_review("alice")), RUN)

    final = workflow.invoke(Command(resume=sign_off("bob")), RUN)

    assert final["status"] == "approved"
    saved = json.loads(Path("data/results/2026Q2/2026Q2-test.json").read_text())
    assert (saved["reviewer"], saved["sign_off"]["signer"]) == ("alice", "bob")


def test_a_paused_run_survives_a_restart(world):
    open_workflow(world).invoke({"quarter": "2026Q2"}, RUN)

    restarted = open_workflow(world)  # new connection, as after closing the program
    restarted.invoke(Command(resume=full_review()), RUN)

    assert pending(restarted)["step"] == "sign_off"


def test_the_reviewers_corrections_reach_the_checks(world, monkeypatch):
    seen = {}

    def spy(quarter, current, previous=None):
        seen["w2"] = {v.field: v for v in current if v.employee_id == "E017"}
        return real_run_checks(quarter, current, previous)

    real_run_checks = workflow_module.run_checks
    monkeypatch.setattr(workflow_module, "run_checks", spy)
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)

    workflow.invoke(Command(resume=full_review("alice")), RUN)

    box_1 = seen["w2"]["w2.box_1"]
    assert (box_1.value, box_1.corrected_by) == (Decimal("1000.00"), "alice")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-500", "abc"])
def test_review_rejects_values_that_are_not_real_amounts(world, bad):
    workflow = open_workflow(world)
    workflow.invoke({"quarter": "2026Q2"}, RUN)
    answer = full_review()
    answer["corrections"][0]["value"] = bad

    workflow.invoke(Command(resume=answer), RUN)

    [problem] = pending(workflow)["problems"]
    assert problem.startswith("w2.box_1 (E017)")


def fake_llm(roster):
    return FakeLLM()


def test_roster_comes_from_the_payroll_snapshot(world):
    roster = load_roster("2026Q2")

    assert len(roster) == 20
    assert roster["E001"] == "Patrick Sanchez"


def test_runner_start_status_and_resume(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    assert run["run_id"].startswith("2026Q2-")
    assert run["quarter"] == "2026Q2"
    assert run_status(run["run_id"])["pending"]["step"] == "review"

    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    assert run["pending"]["step"] == "sign_off"

    run = resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)
    assert (run["status"], run["pending"]) == ("approved", None)


def test_a_finished_run_cannot_be_resumed(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)

    with pytest.raises(ValueError, match="not waiting"):
        resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)


def test_unknown_runs_are_reported(world):
    with pytest.raises(KeyError, match="no-such-run"):
        run_status("no-such-run")


def test_list_runs_shows_every_saved_run(world):
    assert list_runs() == []

    first = start_run("2026Q2", make_llm=fake_llm)
    second = start_run("2026Q2", make_llm=fake_llm)
    resume_run(second["run_id"], full_review("alice"), make_llm=fake_llm)

    runs = {run["run_id"]: run["pending"]["step"] for run in list_runs()}
    assert runs == {first["run_id"]: "review", second["run_id"]: "sign_off"}


def test_review_items_point_at_their_source_page(world):
    run = start_run("2026Q2", make_llm=fake_llm)

    for item in run["pending"]["items"]:
        source = SourceRef(**item["source"])
        assert raw_file(source).name.endswith("_w2_2026_E017.pdf")
        assert source.page == 1


def test_the_signer_sees_each_explanation_and_its_evidence(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)

    for finding in run["pending"]["findings"]:
        assert finding["explanation"]["claims"][0]["evidence_ids"] == ["EV1"]
        assert finding["evidence"][0]["id"] == "EV1"


def test_the_signer_sees_what_the_reviewer_typed_and_where_from(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)

    corrections = run["pending"]["corrections"]
    assert {c["field"] for c in corrections} == set(E017_BOXES)
    for correction in corrections:
        assert (correction["value"], correction["by"]) == ("1000.00", "alice")
        assert correction["machine_value"] is None  # the scan could not be read
        assert SourceRef(**correction["source"]).page == 1


def test_a_signed_run_keeps_what_was_seen_and_decided(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    assert run["record"] is None  # nobody has signed yet
    seen = run["pending"]

    resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)

    record = run_status(run["run_id"])["record"]
    assert (record["reviewer"], record["sign_off"]["signer"]) == ("alice", "bob")
    assert record["sign_off"]["decisions"] == {"F1": "accept", "F2": "accept"}
    for part in ["summary", "corrections", "findings"]:
        assert record[part] == seen[part]  # the record is what bob was shown


def test_a_run_leaves_a_trace_of_what_each_step_did_and_decided(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    [extract] = run["trace"]  # paused: only the first step has finished
    assert extract["step"] == "extract"
    assert "the run pauses for a person" in extract["notes"][0]

    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    resume_run(run["run_id"], sign_off("alice"), make_llm=fake_llm)  # refused
    run = resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)

    trace = {line["step"]: line for line in run["trace"]}
    assert list(trace) == [
        "extract",
        "human_review",
        "compute",
        "explain",
        "summarize",
        "sign_off",
        "finalize",
    ]
    assert trace["human_review"]["did"] == "alice typed 6 values from the source"
    assert trace["compute"]["notes"][0].startswith("F1: Register gross wages")
    assert trace["sign_off"]["did"] == "bob approved the run"
    refused, *decisions = trace["sign_off"]["notes"]
    assert refused.startswith("alice answered and was asked again: maker-checker")
    assert decisions == ["F1: accept", "F2: accept"]
    assert all(line["seconds"] >= 0 for line in run["trace"])


def test_one_connection_can_serve_every_call(world, monkeypatch):
    saver = checkpointer()

    def no_more_connections():
        raise AssertionError("a second connection was opened")

    monkeypatch.setattr(runner, "checkpointer", no_more_connections)

    run = start_run("2026Q2", make_llm=fake_llm, saver=saver)
    assert run_status(run["run_id"], saver)["pending"]["step"] == "review"
    run = resume_run(
        run["run_id"], full_review("alice"), make_llm=fake_llm, saver=saver
    )
    assert [r["run_id"] for r in list_runs(saver)] == [run["run_id"]]


def test_the_version_changes_only_when_the_run_changes(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    assert (
        run_status(run["run_id"])["version"] == run["version"]
    )  # reading changes nothing

    after = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)

    assert after["version"] != run["version"]


def test_an_answer_written_for_an_old_state_is_refused(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    both_saw = run["version"]  # alice and bob both have the review page open
    resume_run(
        run["run_id"], full_review("alice"), make_llm=fake_llm, expected=both_saw
    )
    before = run_status(run["run_id"])

    with pytest.raises(StaleAnswerError):
        resume_run(
            run["run_id"], full_review("bob"), make_llm=fake_llm, expected=both_saw
        )

    after = run_status(run["run_id"])
    assert after["version"] == before["version"]  # bob's late answer changed nothing
    assert after["pending"]["step"] == "sign_off" and "problems" not in after["pending"]


def test_a_refused_answer_also_changes_the_version(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)

    refused = resume_run(run["run_id"], sign_off("alice"), make_llm=fake_llm)

    assert refused["pending"]["problems"]  # maker-checker: asked again
    assert refused["version"] != run["version"]  # so other open pages are out of date


def test_everything_a_run_does_is_written_to_the_audit_log(world):
    run = start_run("2026Q2", make_llm=fake_llm, actor="carol")
    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    resume_run(run["run_id"], sign_off("alice"), make_llm=fake_llm)  # refused
    resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)

    log = read_entries()
    assert [(entry["event"], entry["actor"]) for entry in log] == [
        ("run_started", "carol"),
        ("step_finished", "system"),  # extract
        ("answer_received", "alice"),
        ("step_finished", "system"),  # human_review
        ("step_finished", "system"),  # compute
        ("step_finished", "system"),  # explain
        ("step_finished", "system"),  # summarize
        ("answer_received", "alice"),
        ("answer_refused", "system"),  # maker-checker
        ("answer_received", "bob"),
        ("step_finished", "system"),  # sign_off
        ("step_finished", "system"),  # finalize
        ("run_finished", "system"),
    ]
    assert {entry["details"]["run_id"] for entry in log} == {run["run_id"]}
    assert log[8]["details"]["problems"][0].startswith("maker-checker: alice")
    assert log[-1]["details"]["status"] == "approved"
    assert log[1]["details"]["finished_at"] <= log[1]["at"]  # done, then written down

    assert verify() == []  # and the chain is intact


def test_an_answer_that_came_too_late_is_written_down_too(world):
    run = start_run("2026Q2", make_llm=fake_llm)
    resume_run(
        run["run_id"], full_review("alice"), make_llm=fake_llm, expected=run["version"]
    )

    with pytest.raises(StaleAnswerError):
        resume_run(
            run["run_id"],
            full_review("bob"),
            make_llm=fake_llm,
            expected=run["version"],
        )

    last = read_entries()[-1]
    assert (last["event"], last["actor"]) == ("answer_out_of_date", "bob")


def test_a_run_remembers_what_it_was_made_with(world):
    run = start_run("2026Q2", make_llm=fake_llm)

    made_with = run["made_with"]
    assert made_with["models"] == {"small": "tiny-model", "large": "big-model"}
    assert "explain_finding.v1.md" in made_with["prompts"]
    assert read_entries()[0]["details"]["made_with"] == made_with  # in the log too

    run = resume_run(run["run_id"], full_review("alice"), make_llm=fake_llm)
    resume_run(run["run_id"], sign_off("bob"), make_llm=fake_llm)
    saved = json.loads(
        Path(f"data/results/2026Q2/{run['run_id']}.json").read_text(encoding="utf-8")
    )
    assert saved["made_with"] == made_with  # and in the result file
