from decimal import Decimal

from taxagent.agent.explain import (
    PROMPT_VERSION,
    Claim,
    Explanation,
    explain_finding,
    gather_evidence,
    validate,
)
from taxagent.compute.findings import Finding, run_checks
from taxagent.schema.models import ExtractedValue, SourceRef

HASH = "2" * 64


def value(field, amount, employee_id=None):
    return ExtractedValue(
        field=field,
        employee_id=employee_id,
        value=Decimal(amount),
        confidence=1.0,
        source=SourceRef(file_sha256=HASH, cell="A1"),
    )


def quarter(regular, bonus, line_2):
    gross = str(Decimal(regular) + Decimal(bonus))
    return [
        value("register.regular_wages", regular, "E007"),
        value("register.bonus", bonus, "E007"),
        value("register.gross_wages", gross, "E007"),
        value("payroll_db.gross_wages", gross, "E007"),
        value("form_941.line_2", line_2),
    ]


Q1 = quarter("28375.00", "0.00", "28375.00")
Q2 = quarter("28375.00", "11350.00", "39725.00")
Q2_TYPO = quarter("28375.00", "11350.00", "39995.00")  # 7 and 9 swapped: +270


def labels(evidence):
    return {e.id: e.label for e in evidence}


class FakeLLM:
    """Records what it was asked and returns a canned explanation."""

    def __init__(self, explanation):
        self.explanation = explanation
        self.roster = {"E007": "Patrick Sanchez"}
        self.models = {"large": "big-model"}
        self.calls = []

    def parse(self, role, instructions, prompt, schema):
        self.calls.append((role, instructions, prompt))
        return self.explanation


def test_variance_evidence_shows_both_quarters_line_by_line():
    [bonus] = run_checks("2026Q2", Q2, Q1)

    evidence = gather_evidence(bonus, Q2, Q1)

    text = " | ".join(f"{e.label}={e.value}" for e in evidence)
    assert "register.bonus, E007, 2026Q2=11350.00" in text
    assert "computed change, percent=40.00" in text


def test_code_spots_the_transposition_pattern_not_the_llm():
    [typo] = run_checks("2026Q2", Q2_TYPO, Q1)[:1]

    evidence = gather_evidence(typo, Q2_TYPO, Q1)

    [hint] = [e for e in evidence if "divided by 9" in e.label]
    assert hint.value == Decimal(30)


def test_a_grounded_explanation_has_no_problems():
    [bonus] = run_checks("2026Q2", Q2, Q1)
    evidence = gather_evidence(bonus, Q2, Q1)
    ids = labels(evidence)
    bonus_id = next(
        i
        for i, label in ids.items()
        if label.startswith("register.bonus, E007, 2026Q2")
    )
    good = Explanation(
        claims=[
            Claim(
                text="A bonus of 11,350.00 was paid in 2026Q2.", evidence_ids=[bonus_id]
            )
        ],
        can_determine_cause=True,
    )

    assert validate(good, evidence, bonus) == []


def test_uncited_claims_are_flagged():
    [bonus] = run_checks("2026Q2", Q2, Q1)
    evidence = gather_evidence(bonus, Q2, Q1)
    lazy = Explanation(
        claims=[Claim(text="Wages went up.", evidence_ids=[])], can_determine_cause=True
    )

    assert validate(lazy, evidence, bonus) == ["uncited claim: 'Wages went up.'"]


def test_citing_evidence_that_was_never_given_is_flagged():
    [bonus] = run_checks("2026Q2", Q2, Q1)
    evidence = gather_evidence(bonus, Q2, Q1)
    invented = Explanation(
        claims=[Claim(text="See the HR memo.", evidence_ids=["EV99"])],
        can_determine_cause=False,
    )

    assert validate(invented, evidence, bonus) == [
        "cites evidence that was never given: EV99"
    ]


def test_numbers_the_llm_made_up_are_flagged():
    [bonus] = run_checks("2026Q2", Q2, Q1)
    evidence = gather_evidence(bonus, Q2, Q1)
    maths = Explanation(
        claims=[Claim(text="That is about 3,783 per month.", evidence_ids=["EV1"])],
        can_determine_cause=True,
    )

    [problem] = validate(maths, evidence, bonus)
    assert problem.startswith("number 3783 is not in the evidence")


def test_numbers_inside_names_are_not_false_alarms():
    typo = Finding(
        kind="reconciliation",
        check="register_vs_941_wages",
        quarter="2026Q2",
        summary="Register vs Form 941 line 2",
        difference=Decimal(270),
        sources=(SourceRef(file_sha256=HASH, cell="A1"),),
    )
    evidence = gather_evidence(typo, Q2_TYPO, Q1)
    named = Explanation(
        claims=[Claim(text="Form 941 line 2 differs by 270.", evidence_ids=["EV1"])],
        can_determine_cause=False,
    )

    assert validate(named, evidence, typo) == []


def test_explain_finding_uses_the_large_model_and_records_versions():
    [bonus] = run_checks("2026Q2", Q2, Q1)
    answer = Explanation(
        claims=[Claim(text="A bonus was paid.", evidence_ids=["EV5"])],
        can_determine_cause=True,
    )
    llm = FakeLLM(answer)

    result = explain_finding(llm, bonus, Q2, Q1)

    [(role, instructions, prompt)] = llm.calls
    assert role == "large"
    assert "Use ONLY the listed evidence" in instructions
    assert "EV5: register.bonus, E007, 2026Q2 = 11,350.00" in prompt
    assert (result.prompt_version, result.model) == (PROMPT_VERSION, "big-model")
    assert result.problems == ()
