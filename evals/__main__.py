"""Run the evals and print the scores.

uv run python -m evals          the free ones: detection and extraction
uv run python -m evals --llm    also the AI's explanations (calls the paid API)
"""

import argparse
import os

from dotenv import load_dotenv

from evals.detection import run_detection
from evals.explanations import run_explanation_eval
from evals.extraction import run_extraction_eval
from evals.report import compare, latest_report, save_report


def show_detection(result: dict) -> None:
    print("Detection: does the pipeline find the planted errors, and nothing else?")
    for error in result["errors"]:
        mark = "found " if error["found"] else "MISSED"
        print(f"  {mark}  #{error['id']} {error['type']}: {error['cause']}")
    for signal in result["unexpected"]:
        print(f"  UNEXPECTED  {signal}")
    print(f"  recall {result['recall']:.0%}   precision {result['precision']:.0%}")


def show_extraction(result: dict) -> None:
    print("Extraction: is every value read exactly as its document shows it?")
    for document, counts in result["documents"].items():
        total = sum(counts.values())
        others = ", ".join(
            f"{n} {kind}" for kind, n in counts.items() if kind != "correct"
        )
        print(f"  {document:<11} {counts.get('correct', 0)}/{total} correct  {others}")
    print(f"  accuracy {result['accuracy']:.1%}")
    print(f"  confidently wrong: {result['confidently_wrong']}  (must be 0)")
    print(f"  invented values:   {len(result['invented'])}  (must be 0)")


def show_explanations(result: dict) -> None:
    print(f"Explanations: {result['model']}, {result['calls']} calls")
    for row in result["findings"]:
        verdicts = ", ".join(f"{n}x {kind}" for kind, n in row["verdicts"].items())
        print(f"  {row['finding']}")
        print(f"    expected: {row['expected']}")
        print(
            f"    {verdicts}   grounded {row['grounded']:.0%}   "
            f"consistent {row['consistent']:.0%}   {row['seconds']:.1f} s per call"
        )
        for answer in row["answers"]:
            if answer["verdict"] == "wrong cause":  # show it: the grader may be wrong
                print(f"      wrong cause said: {answer['text']}")
    print(f"  acceptable (right, or honest it can't tell): {result['acceptable']:.0%}")
    print(
        f"  wrong cause: {result['wrong']}   names leaked: {result['leaks']}  (must be 0)"
    )
    print(f"  grounded {result['grounded']:.0%}   total {result['seconds']:.0f} s")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m evals")
    parser.add_argument(
        "--llm", action="store_true", help="also evaluate the AI (calls the paid API)"
    )
    args = parser.parse_args(argv)
    load_dotenv()  # the API key and the model names live in .env

    results = {
        "detection": run_detection(),
        "extraction": run_extraction_eval(),
        "explanations": run_explanation_eval() if args.llm else None,
    }
    show_detection(results["detection"])
    print()
    show_extraction(results["extraction"])
    print()
    if results["explanations"]:
        show_explanations(results["explanations"])
    else:
        print("Explanations: skipped, they call the paid API. Add --llm to run them.")

    before = latest_report()
    models = {
        role: os.environ.get(f"MODEL_{role.upper()}") for role in ("small", "large")
    }
    path = save_report(results, models)
    print()
    print(f"Saved {path.as_posix()}")
    if before:
        changes = compare(before, results)
        print(
            "Changed since the last report:"
            if changes
            else "No change since the last report."
        )
        for line in changes:
            print(f"  {line}")


if __name__ == "__main__":
    main()
