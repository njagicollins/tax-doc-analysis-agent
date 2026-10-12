import json

import pytest

from taxagent.audit.log import append_event, read_entries
from taxagent.audit.view import audit_rows, made_with, said
from taxagent.cli import main


def an_entry(event, details, actor="system", seq=1):
    return {
        "seq": seq,
        "at": "2026-10-12T09:30:15.123456+00:00",
        "event": event,
        "actor": actor,
        "details": details,
    }


INGESTED = {
    "ingest_run": "i1",
    "quarter": "2026Q2",
    "new": 2,
    "unchanged": 21,
    "changed": ["a.pdf"],
}


@pytest.mark.parametrize(
    ("event", "details", "sentence"),
    [
        ("run_started", {"quarter": "2026Q2"}, "Started a run for 2026Q2"),
        ("answer_received", {"asked": "review"}, "Answered the review request"),
        (
            "answer_refused",
            {"problems": ["F1 needs a decision", "approve must be true or false"]},
            "Answer refused: F1 needs a decision; approve must be true or false",
        ),
        (
            "step_finished",
            {"step": "compute", "did": "Ran the checks"},
            "compute: Ran the checks",
        ),
        ("run_finished", {"status": "approved"}, "Run approved"),
        ("files_ingested", INGESTED, "Ingested 2026Q2: 2 new, 21 unchanged, 1 changed"),
        ("something_new", {}, "something_new"),
    ],
)
def test_each_event_is_said_in_one_sentence(event, details, sentence):
    assert said(an_entry(event, details)) == sentence


def test_rows_show_when_who_what_and_which_run():
    entry = an_entry("run_finished", {"run_id": "r1", "status": "rejected"}, seq=7)

    assert audit_rows([entry]) == [
        {
            "#": 7,
            "when (UTC)": "2026-10-12 09:30:15",
            "who": "system",
            "what": "Run rejected",
            "run": "r1",
        }
    ]


def test_rows_can_be_limited_to_one_run():
    entries = [
        an_entry("run_started", {"run_id": "r1", "quarter": "2026Q2"}, seq=1),
        an_entry("run_started", {"run_id": "r2", "quarter": "2026Q2"}, seq=2),
        an_entry("run_finished", {"run_id": "r1", "status": "approved"}, seq=3),
    ]

    assert [row["#"] for row in audit_rows(entries, "r1")] == [1, 3]
    assert len(audit_rows(entries)) == 3


def test_what_a_run_was_made_with_comes_from_its_first_entry():
    new = {"run_id": "r1", "quarter": "2026Q2", "made_with": {"models": {}}}
    old = {"run_id": "old", "quarter": "2026Q2"}  # started before this was recorded
    entries = [an_entry("run_started", new), an_entry("run_started", old)]

    assert made_with(entries, "r1") == {"models": {}}
    assert made_with(entries, "old") is None
    assert made_with(entries, "no-such-run") is None


def test_the_audit_command_reports_an_intact_log(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    last = append_event("run_started", "alice", {"run_id": "r1", "quarter": "2026Q2"})

    main(["audit"])

    printed = capsys.readouterr().out
    assert "1 entries" in printed and "Intact" in printed
    assert last["hash"] in printed  # so it can be kept somewhere else


def test_the_audit_command_fails_loudly_on_a_changed_log(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    append_event("run_started", "alice", {"run_id": "r1", "quarter": "2026Q2"})
    [entry] = read_entries()
    entry["actor"] = "bob"
    (tmp_path / "data/audit/audit.jsonl").write_text(json.dumps(entry) + "\n")

    with pytest.raises(SystemExit) as stopped:
        main(["audit"])

    assert stopped.value.code == 1  # other programs can tell it failed
    assert "entry 1 was changed after it was written" in capsys.readouterr().out


def test_the_audit_command_notices_a_log_cut_short(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    append_event("run_started", "alice", {"run_id": "r1", "quarter": "2026Q2"})

    with pytest.raises(SystemExit):
        main(["audit", "--last-hash", "f" * 64])  # the outside copy says otherwise
