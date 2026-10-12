import subprocess

from taxagent.audit import provenance as provenance_module
from taxagent.audit.provenance import code_version, prompt_fingerprints, provenance


def test_a_prompt_edited_without_renaming_gets_a_new_fingerprint(tmp_path):
    prompt = tmp_path / "explain_finding.v1.md"
    prompt.write_text("Explain the finding.", encoding="utf-8")
    before = prompt_fingerprints(tmp_path)

    prompt.write_text("Explain the finding. Be brief.", encoding="utf-8")
    after = prompt_fingerprints(tmp_path)

    assert list(before) == list(after) == ["explain_finding.v1.md"]  # same name
    assert before != after  # different text


def test_the_same_prompt_text_always_has_the_same_fingerprint(tmp_path):
    (tmp_path / "a.v1.md").write_text("Same words.", encoding="utf-8")

    assert prompt_fingerprints(tmp_path) == prompt_fingerprints(tmp_path)


def test_the_real_prompts_are_all_fingerprinted():
    assert set(prompt_fingerprints()) == {
        "draft_summary.v1.md",
        "explain_finding.v1.md",
    }


def test_provenance_names_the_code_prompts_models_and_settings():
    made_with = provenance({"small": "tiny-model", "large": "big-model"})

    assert set(made_with) == {"code", "prompts", "models", "settings"}
    assert made_with["models"]["large"] == "big-model"
    assert made_with["settings"]["variance_threshold_pct"] == "25"
    assert isinstance(made_with["code"]["commit"], str)


def test_without_git_the_code_version_is_unknown_not_a_crash(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)

    assert code_version() == {"commit": "unknown", "uncommitted_changes": None}
    assert provenance_module.git("status") is None
