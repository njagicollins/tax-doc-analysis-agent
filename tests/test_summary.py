from taxagent.agent.explain import Claim
from taxagent.agent.summary import Summary, render_prompt, validate

EXPLAINED = [
    {
        "finding_id": "F1",
        "finding": {"summary": "Register 519,475.00 vs Form 941 line 2 519,745.00"},
        "explanation": {"claims": [{"text": "The difference is 270.00."}]},
    }
]
SHOWN = render_prompt("2026Q2", EXPLAINED)


def summary(*claims):
    return Summary(claims=[Claim(text=text, evidence_ids=ids) for text, ids in claims])


def test_numbers_the_model_was_shown_are_fine():
    good = summary(("F1: the 941 is 270.00 above the register.", ["F1"]))

    assert validate(good, {"F1"}, SHOWN) == []


def test_restated_numbers_are_flagged():
    rounded = summary(("The 941 is about 300 too high.", ["F1"]))

    [problem] = validate(rounded, {"F1"}, SHOWN)
    assert problem.startswith("number 300 was not in the findings")


def test_an_empty_summary_is_flagged():
    assert validate(summary(), {"F1"}, SHOWN) == ["the summary makes no claims"]


def test_unknown_finding_ids_are_flagged():
    invented = summary(("See F9.", ["F9"]))

    assert validate(invented, {"F1"}, SHOWN) == [
        "cites a finding that does not exist: F9"
    ]
