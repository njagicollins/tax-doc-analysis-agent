import json

from taxagent.review.dashboard import (
    CHECKS,
    TYPED_IN,
    check_status,
    counts_by_category,
    load_results,
    official,
)


def a_result(run_id, status="approved", findings=(), corrections=0):
    """A saved result with only the parts the dashboard reads."""
    return {
        "run_id": run_id,
        "quarter": run_id.split("-")[0],
        "status": status,
        "findings": [
            {"id": f"F{n}", "finding": {"kind": kind, "check": check}}
            for n, (kind, check) in enumerate(findings, start=1)
        ],
        "corrections": [{"field": f"w2.box_{n}"} for n in range(corrections)],
    }


WAGES_OFF = ("reconciliation", "register_vs_941_wages")
BIG_RAISE = ("variance", "quarter_over_quarter_gross_wages")


def test_the_latest_approved_run_is_the_official_one():
    results = [
        a_result("2026Q2-20261002T100000Z-aaaa"),
        a_result("2026Q2-20261011T100000Z-bbbb"),
        a_result("2026Q2-20261012T100000Z-cccc", status="rejected"),
    ]

    assert official(results)["2026Q2"]["run_id"].endswith("bbbb")


def test_a_quarter_with_no_approved_run_has_no_official_result():
    results = [a_result("2026Q1-20261011T100000Z-aaaa", status="rejected")]

    assert official(results) == {}


def test_each_quarter_has_its_own_official_result():
    results = [
        a_result("2026Q1-20260701T100000Z-aaaa"),
        a_result("2026Q2-20261011T100000Z-bbbb"),
    ]

    assert set(official(results)) == {"2026Q1", "2026Q2"}


def test_every_check_is_listed_as_pass_or_fail():
    status = check_status(
        a_result("2026Q2-x", findings=[WAGES_OFF, BIG_RAISE, BIG_RAISE])
    )

    assert len(status) == len(CHECKS)
    failed = {
        row["check"]: row["findings"] for row in status if row["result"] == "fail"
    }
    assert failed == {
        CHECKS["register_vs_941_wages"]: 1,
        CHECKS["quarter_over_quarter_gross_wages"]: 2,
    }


def test_a_clean_run_passes_every_check():
    status = check_status(a_result("2026Q2-x"))

    assert {row["result"] for row in status} == {"pass"}


def test_categories_are_counted():
    result = a_result(
        "2026Q2-x", findings=[WAGES_OFF, BIG_RAISE, BIG_RAISE], corrections=6
    )

    assert counts_by_category(result) == {
        "Totals don't match": 1,
        "Large change since last quarter": 2,
        TYPED_IN: 6,
    }


def test_a_clean_run_has_nothing_to_count():
    assert counts_by_category(a_result("2026Q2-x")) == {}


def test_results_are_read_from_every_quarters_folder(tmp_path):
    for run_id in ["2026Q1-a", "2026Q2-b"]:
        folder = tmp_path / run_id.split("-")[0]
        folder.mkdir()
        (folder / f"{run_id}.json").write_text(json.dumps(a_result(run_id)))

    assert [r["run_id"] for r in load_results(tmp_path)] == ["2026Q1-a", "2026Q2-b"]
