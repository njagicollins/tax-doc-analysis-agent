"""Explain a finding with the LLM, then check the explanation from the outside.

The LLM only sees numbered evidence (EV1, EV2, ...) built from our own extracted
and computed values. Its answer is flagged if a claim cites nothing, cites
evidence we never gave it, or quotes a number that is not in the evidence.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pydantic import BaseModel

from taxagent.agent.llm import LLM
from taxagent.agent.pii import mask
from taxagent.compute.findings import Finding, by_employee, select
from taxagent.compute.traced import Traced, total, traced
from taxagent.schema.models import ExtractedValue, SourceRef

PROMPT_VERSION = "explain_finding.v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"

# A number not glued to letters, so "E007" and "2026Q2" are not read as numbers
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")


class Claim(BaseModel):
    text: str
    evidence_ids: list[str]


class Explanation(BaseModel):
    claims: list[Claim]
    can_determine_cause: bool


@dataclass(frozen=True)
class Evidence:
    id: str
    label: str
    value: Decimal
    sources: tuple[SourceRef, ...]


@dataclass(frozen=True)
class ExplainedFinding:
    finding: Finding
    explanation: Explanation
    evidence: tuple[Evidence, ...]
    problems: tuple[str, ...]  # empty = passed every check
    prompt_version: str
    model: str


Fact = tuple[str, Traced]  # (label, amount with its sources)


def employee_facts(
    values: list[ExtractedValue], employee_id: str, when: str
) -> list[Fact]:
    facts = []
    for field in ["register.regular_wages", "register.bonus", "register.gross_wages"]:
        line = by_employee(values, field).get(employee_id)
        if line is not None:
            facts.append((f"{field}, {employee_id}, {when}", traced(line)))
    return facts


def reconciliation_facts(finding: Finding, values: list[ExtractedValue]) -> list[Fact]:
    register = total(select(values, "register.gross_wages"))
    payroll_db = total(select(values, "payroll_db.gross_wages"))
    if finding.check == "register_vs_941_wages":
        [line_2] = select(values, "form_941.line_2")
        other: Fact = ("Form 941 line 2 (wages)", traced(line_2))
    else:
        other = ("payroll database gross wages, all employees", payroll_db)

    def count(field: str, sources: tuple[SourceRef, ...]) -> Traced:
        return Traced(Decimal(len(by_employee(values, field))), sources)

    return [
        ("register gross wages, all employees", register),
        other,
        ("employees in the register", count("register.gross_wages", register.sources)),
        (
            "employees in the payroll database",
            count("payroll_db.gross_wages", payroll_db.sources),
        ),
    ]


TRANSPOSITION_HINT = (
    "difference divided by 9 (a whole result is typical of two swapped digits)"
)


def pattern_hints(finding: Finding) -> list[Fact]:
    """Patterns the code can prove, so the LLM never has to compute them."""
    difference = finding.difference
    if finding.kind == "reconciliation" and difference and difference % 9 == 0:
        return [(TRANSPOSITION_HINT, Traced(abs(difference) / 9, finding.sources))]
    return []


def gather_evidence(
    finding: Finding,
    current: list[ExtractedValue],
    previous: list[ExtractedValue] | None,
) -> list[Evidence]:
    """Pick the facts a human would look at for this kind of finding."""
    facts: list[Fact] = []
    if finding.kind == "variance" and previous is not None:
        facts += employee_facts(previous, finding.employee_id, "previous quarter")
        facts += employee_facts(current, finding.employee_id, finding.quarter)
    elif finding.kind == "reconciliation":
        facts += reconciliation_facts(finding, current)
    elif finding.kind in ("missing_employee", "extra_employee"):
        facts += employee_facts(current, finding.employee_id, finding.quarter)
        db_line = by_employee(current, "payroll_db.gross_wages").get(
            finding.employee_id
        )
        if db_line is not None:
            label = f"payroll database gross wages, {finding.employee_id}"
            facts.append((label, traced(db_line)))

    # The judge's own numbers, so the LLM can quote them instead of computing them
    if finding.difference is not None:
        facts.append(
            ("computed difference", Traced(finding.difference, finding.sources))
        )
    if finding.change_pct is not None:
        facts.append(
            ("computed change, percent", Traced(finding.change_pct, finding.sources))
        )
    facts += pattern_hints(finding)

    return [
        Evidence(f"EV{number}", label, amount.value, amount.sources)
        for number, (label, amount) in enumerate(facts, start=1)
    ]


def render_prompt(finding: Finding, evidence: list[Evidence]) -> str:
    lines = [f"Finding ({finding.kind}, {finding.quarter}): {finding.summary}", ""]
    lines += ["Evidence:"] + [f"{e.id}: {e.label} = {e.value:,}" for e in evidence]
    return "\n".join(lines)


def numbers_in(text: str) -> set[Decimal]:
    found = set()
    for token in NUMBER.findall(text):
        try:
            found.add(abs(Decimal(token.replace(",", ""))))
        except InvalidOperation:
            continue
    return found


def validate(
    explanation: Explanation, evidence: list[Evidence], finding: Finding
) -> list[str]:
    """Check the answer from the outside. Never trust the model's word about itself."""
    known_ids = {e.id for e in evidence}
    # Amounts from the evidence, plus numbers that are names ("Form 941", "line 2")
    known_numbers = {abs(e.value) for e in evidence}
    for text in [finding.summary, *(e.label for e in evidence)]:
        known_numbers |= numbers_in(text)

    problems = []
    if not explanation.claims:
        problems.append("the explanation makes no claims")
    for claim in explanation.claims:
        if not claim.evidence_ids:
            problems.append(f"uncited claim: {claim.text!r}")
        for evidence_id in claim.evidence_ids:
            if evidence_id not in known_ids:
                problems.append(f"cites evidence that was never given: {evidence_id}")
        for number in numbers_in(claim.text) - known_numbers:
            problems.append(f"number {number} is not in the evidence: {claim.text!r}")
    return problems


def explain_finding(
    llm: LLM,
    finding: Finding,
    current: list[ExtractedValue],
    previous: list[ExtractedValue] | None = None,
) -> ExplainedFinding:
    evidence = gather_evidence(finding, current, previous)
    prompt = mask(render_prompt(finding, evidence), llm.roster)
    instructions = PROMPT_PATH.read_text(encoding="utf-8")
    explanation = llm.parse("large", instructions, prompt, Explanation)
    return ExplainedFinding(
        finding=finding,
        explanation=explanation,
        evidence=tuple(evidence),
        problems=tuple(validate(explanation, evidence, finding)),
        prompt_version=PROMPT_VERSION,
        model=llm.models["large"],
    )
