"""Run the evals and print the scores: uv run python -m evals"""

from evals.detection import run_detection
from evals.extraction import run_extraction_eval


def main() -> None:
    result = run_detection()

    print("Detection: does the pipeline find the planted errors, and nothing else?")
    for error in result["errors"]:
        mark = "found " if error["found"] else "MISSED"
        print(f"  {mark}  #{error['id']} {error['type']}: {error['cause']}")
    for signal in result["unexpected"]:
        print(f"  UNEXPECTED  {signal}")
    print(f"  recall {result['recall']:.0%}   precision {result['precision']:.0%}")

    result = run_extraction_eval()

    print()
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


if __name__ == "__main__":
    main()
