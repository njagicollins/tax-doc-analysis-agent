"""Draft the quarter's summary with the LLM, citing finding IDs (F1, F2, ...)."""

from pathlib import Path

from pydantic import BaseModel

from taxagent.agent.explain import Claim, numbers_in
from taxagent.agent.llm import LLM
from taxagent.agent.pii import mask

PROMPT_VERSION = "draft_summary.v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"


class Summary(BaseModel):
    claims: list[Claim]  # here evidence_ids are finding IDs


def render_prompt(quarter: str, explained: list[dict]) -> str:
    lines = [f"Quarter {quarter}: {len(explained)} findings.", ""]
    for item in explained:
        lines.append(f"{item['finding_id']}: {item['finding']['summary']}")
        for claim in item["explanation"]["claims"]:
            lines.append(f"  - {claim['text']}")
    return "\n".join(lines)


def validate(summary: Summary, finding_ids: set[str], shown: str) -> list[str]:
    """The same outside checks as explanations: citations and numbers."""
    known_numbers = numbers_in(shown)  # every number the model was shown

    problems = []
    if not summary.claims:
        problems.append("the summary makes no claims")
    for claim in summary.claims:
        if not claim.evidence_ids:
            problems.append(f"uncited claim: {claim.text!r}")
        for finding_id in claim.evidence_ids:
            if finding_id not in finding_ids:
                problems.append(f"cites a finding that does not exist: {finding_id}")
        for number in numbers_in(claim.text) - known_numbers:
            problems.append(f"number {number} was not in the findings: {claim.text!r}")
    return problems


def draft_summary(llm: LLM, quarter: str, explained: list[dict]) -> dict:
    shown = render_prompt(quarter, explained)
    instructions = PROMPT_PATH.read_text(encoding="utf-8")
    summary = llm.parse("large", instructions, mask(shown, llm.roster), Summary)
    finding_ids = {item["finding_id"] for item in explained}
    return {
        "claims": [claim.model_dump() for claim in summary.claims],
        "problems": validate(summary, finding_ids, shown),
        "prompt_version": PROMPT_VERSION,
        "model": llm.models["large"],
    }
