"""Explanation eval: are the AI's explanations grounded, right, steady and safe?

Unlike the other evals this one calls the real model, so it costs money and its
answer can change from one run to the next. That is why each finding is asked
several times: one good answer proves little about the next one.
"""

import json
import tempfile
import time
from collections import Counter
from pathlib import Path

from evals.detection import GOLDEN_PATH, Signal, expected
from taxagent.agent.explain import explain_finding
from taxagent.agent.llm import llm_from_env
from taxagent.agent.roster import load_roster
from taxagent.agent.runner import MakeLLM
from taxagent.compute.findings import run_checks
from taxagent.extraction.run import run_extraction

# Words that show the explanation named the planted cause
CAUSE_WORDS = {
    "reconciliation_mismatch": ["transpos", "swapped"],
    "missing_employee": ["missing", "left out", "omitted", "not in the register"],
    "variance": ["bonus"],
}
# For these, the evidence shows the cause, so "I can't tell" is too cautious
SHOWN_IN_EVIDENCE = {"missing_employee", "variance"}


def verdict(text: str, can_determine_cause: bool, words: list[str], shown: bool) -> str:
    """How one explanation did on the cause."""
    if any(word in text.lower() for word in words):
        return "right cause"
    if not can_determine_cause:
        return "too cautious" if shown else "honest: can't tell"
    return "wrong cause"  # claimed to know, and named something else


def causes(errors: list[dict], quarters: list[str]) -> dict[Signal, tuple[dict, bool]]:
    """For each signal a planted error raises: that error, and is it the real cause?"""
    found = {}
    for error in errors:
        must, may = expected(error, quarters)
        found |= {signal: (error, True) for signal in must}
        found |= {signal: (error, False) for signal in may}  # side effects
    return found


def run_explanation_eval(
    make_llm: MakeLLM = llm_from_env, repeats: int = 3, golden_path: Path = GOLDEN_PATH
) -> dict:
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    quarters = sorted(golden["quarters"])
    planted = causes(golden["planted_errors"], quarters)

    rows, previous = [], None
    with tempfile.TemporaryDirectory() as scratch:  # an eval must not touch saved data
        for quarter in quarters:
            roster = load_roster(quarter)
            llm = make_llm(roster)
            values = run_extraction(quarter, extracted_dir=Path(scratch)).values
            for finding in run_checks(quarter, values, previous):
                signal = Signal(
                    finding.quarter, finding.kind, finding.check, finding.employee_id
                )
                error, is_cause = planted[signal]
                words = CAUSE_WORDS[error["type"]]
                shown = is_cause and error["type"] in SHOWN_IN_EVIDENCE

                verdicts, grounded, leaks, seconds = Counter(), 0, 0, 0.0
                answers = []
                for _ in range(repeats):
                    started = time.perf_counter()
                    result = explain_finding(llm, finding, values, previous)
                    seconds += time.perf_counter() - started
                    text = " ".join(claim.text for claim in result.explanation.claims)
                    can_tell = result.explanation.can_determine_cause
                    said = verdict(text, can_tell, words, shown)
                    verdicts[said] += 1
                    answers.append(
                        {
                            "verdict": said,
                            "can_determine_cause": can_tell,
                            "text": text,
                            "problems": list(result.problems),
                        }
                    )
                    grounded += not result.problems
                    leaks += sum(name in text for name in roster.values())
                rows.append(
                    {
                        "finding": finding.summary,
                        "expected": error["cause"] if is_cause else "side effect",
                        "verdicts": dict(verdicts),
                        "grounded": grounded / repeats,
                        "consistent": max(verdicts.values()) / repeats,
                        "leaks": leaks,
                        "seconds": seconds / repeats,
                        "answers": answers,
                    }
                )
            previous = values

    calls = len(rows) * repeats
    good = sum(
        row["verdicts"].get("right cause", 0)
        + row["verdicts"].get("honest: can't tell", 0)
        for row in rows
    )
    return {
        "model": llm.models["large"],
        "findings": rows,
        "calls": calls,
        "acceptable": good / calls,  # right, or honest that it could not tell
        "wrong": sum(row["verdicts"].get("wrong cause", 0) for row in rows),
        "grounded": sum(row["grounded"] for row in rows) / len(rows),
        "leaks": sum(row["leaks"] for row in rows),
        "seconds": sum(row["seconds"] * repeats for row in rows),
    }
