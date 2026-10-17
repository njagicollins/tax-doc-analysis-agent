from evals.explanations import causes, run_explanation_eval, verdict
from taxagent.agent.explain import Claim, Explanation
from tests.test_workflow import fake_llm, world  # noqa: F401

BONUS_WORDS = ["bonus"]


def test_naming_the_cause_is_right_even_when_hedged():
    text = "The 11,350.00 bonus explains the increase."

    assert verdict(text, True, BONUS_WORDS, shown=True) == "right cause"
    assert verdict(text, False, BONUS_WORDS, shown=True) == "right cause"


def test_not_knowing_is_honest_only_when_the_evidence_cannot_show_the_cause():
    text = "The totals differ; a person should compare the two documents."

    assert verdict(text, False, ["transpos"], shown=False) == "honest: can't tell"
    assert verdict(text, False, BONUS_WORDS, shown=True) == "too cautious"


def test_claiming_to_know_and_naming_something_else_is_wrong():
    text = "The increase is due to a promotion."

    assert verdict(text, True, BONUS_WORDS, shown=True) == "wrong cause"


def test_side_effects_are_told_apart_from_real_causes():
    left_out = {
        "id": 2,
        "type": "missing_employee",
        "quarter": "2026Q1",
        "employee_id": "E013",
        "cause": "left out",
    }

    found = causes([left_out], ["2026Q1"])

    assert sorted(is_cause for _, is_cause in found.values()) == [False, False, True]


class NamingLLM:
    """A model that leaks a name: the eval must notice."""

    def __init__(self, roster):
        self.roster = roster
        self.models = {"small": "tiny-model", "large": "leaky-model"}
        self.name = next(iter(roster.values()))

    def parse(self, role, instructions, prompt, schema):
        claim = Claim(text=f"{self.name} received a bonus.", evidence_ids=["EV1"])
        return Explanation(claims=[claim], can_determine_cause=True)


def test_every_finding_is_asked_several_times(world):  # noqa: F811
    result = run_explanation_eval(make_llm=fake_llm, repeats=2)

    assert result["calls"] == len(result["findings"]) * 2
    assert len(result["findings"]) == 5  # three in Q1, two in Q2
    assert result["leaks"] == 0
    assert result["grounded"] == 1.0  # the fake cites EV1 and quotes no numbers


def test_a_fake_that_never_knows_is_too_cautious_where_the_evidence_shows_why(world):  # noqa: F811
    result = run_explanation_eval(make_llm=fake_llm, repeats=1)

    bonus = next(row for row in result["findings"] if "E007" in row["finding"])
    assert bonus["verdicts"] == {"too cautious": 1}


def test_a_leaked_name_is_counted(world):  # noqa: F811
    result = run_explanation_eval(make_llm=NamingLLM, repeats=1)

    assert result["leaks"] == len(result["findings"])  # one name in every answer
    assert result["model"] == "leaky-model"


def test_every_answer_is_kept_word_for_word(world):  # noqa: F811
    result = run_explanation_eval(make_llm=fake_llm, repeats=2)

    answers = result["findings"][0]["answers"]
    assert len(answers) == 2  # one per time it was asked, none thrown away
    assert answers[0]["text"] == "See the evidence."  # what the fake said
    assert answers[0]["verdict"] == "honest: can't tell"
