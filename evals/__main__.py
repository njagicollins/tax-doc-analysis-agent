"""Run the evals and print the scores: uv run python -m evals"""

from evals.detection import run_detection


def main() -> None:
    result = run_detection()

    print("Detection: does the pipeline find the planted errors, and nothing else?")
    for error in result["errors"]:
        mark = "found " if error["found"] else "MISSED"
        print(f"  {mark}  #{error['id']} {error['type']}: {error['cause']}")
    for signal in result["unexpected"]:
        print(f"  UNEXPECTED  {signal}")
    print(f"  recall {result['recall']:.0%}   precision {result['precision']:.0%}")


if __name__ == "__main__":
    main()
