import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from synthetic.__main__ import main as generate_everything
from taxagent.agent import workflow as workflow_module
from taxagent.agent.explain import Claim, Explanation
from taxagent.agent.summary import Summary
from taxagent.agent.workflow import build_workflow
from taxagent.extraction.run import run_extraction
from taxagent.ingestion.pipeline import ingest
from taxagent.ingestion.sources import SqlPayrollSource

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
