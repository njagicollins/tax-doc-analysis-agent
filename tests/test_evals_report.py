import json

from evals.__main__ import main
from evals.report import compare, headlines, latest_report, save_report
from tests.test_workflow import world  # noqa: F401

MODELS = {"small": "tiny-model", "large": "big-model"}


def a_report(accuracy=0.984, explanations=None):
    return {
        "detection": {"recall": 1.0, "precision": 1.0},
        "extraction": {"accuracy": accuracy, "confidently_wrong": 0},
        "explanations": explanations,
    }


def test_a_report_is_saved_with_what_produced_it(tmp_path):
    path = save_report(a_report(), MODELS, reports_dir=tmp_path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["extraction"]["accuracy"] == 0.984
    assert saved["made_with"]["models"] == MODELS
    assert "explain_finding.v1.md" in saved["made_with"]["prompts"]
    assert path.name.endswith("Z.json")  # named by the time, in UTC


def test_the_latest_report_is_the_newest_file(tmp_path):
    assert latest_report(tmp_path) is None
    (tmp_path / "20261001T000000Z.json").write_text(json.dumps({"n": 1}))
    (tmp_path / "20261014T000000Z.json").write_text(json.dumps({"n": 2}))

    assert latest_report(tmp_path) == {"n": 2}


def test_an_eval_that_was_not_run_has_no_numbers():
    numbers = headlines(a_report())

    assert numbers["extraction accuracy"] == 0.984
    assert numbers["wrong causes"] is None  # --llm was not used


def test_only_changed_numbers_are_reported():
    before = a_report(accuracy=0.984)
    after = a_report(accuracy=0.95)

    assert compare(before, after) == ["extraction accuracy: 0.984 -> 0.95"]
    assert compare(before, before) == []


def test_numbers_missing_from_either_report_are_not_compared():
    with_llm = a_report(explanations={"acceptable": 0.93, "wrong": 1})

    assert compare(a_report(), with_llm) == []


def test_running_the_evals_saves_a_report(world, capsys):  # noqa: F811
    main([])

    saved = latest_report()
    assert saved["detection"]["recall"] == 1.0
    assert saved["explanations"] is None  # not asked for
    assert "Saved data/evals/" in capsys.readouterr().out
