import pytest

from taxagent.agent.trace import duration, ingest_line, traced, with_waits
from taxagent.ingestion.manifest import ManifestRow


def test_a_traced_step_leaves_a_line_and_keeps_its_result():
    def count(state):
        return {"total": state["a"] + 1, "did": "Added one"}

    update = traced("count", count)({"a": 1}, None)

    [line] = update["trace"]
    assert update["total"] == 2 and "did" not in update
    assert (line["step"], line["did"]) == ("count", "Added one")
    assert line["seconds"] >= 0 and line["finished_at"].endswith("+00:00")


def test_a_step_that_wants_the_config_gets_it():
    def save(state, config):
        return {"did": f"Saved {config['name']}"}

    update = traced("save", save)({}, {"name": "run-1"})

    assert update["trace"][0]["did"] == "Saved run-1"


def a_row(run_id, name, fetched_at, is_new=True, quarter="2026Q2"):
    return ManifestRow(
        run_id=run_id,
        source="adp",
        name=name,
        path=f"data/raw/{quarter}/abc_{name}",
        sha256="0" * 64,
        size_bytes=1,
        is_new=is_new,
        fetched_at=fetched_at,
    )


ROWS = [
    a_row("ingest-1", "a.pdf", "2026-10-01T10:00:00+00:00"),
    a_row("ingest-2", "a.pdf", "2026-10-05T10:00:00+00:00", is_new=False),
    a_row("ingest-2", "b.pdf", "2026-10-05T10:00:02.500000+00:00"),
    a_row("ingest-3", "a.pdf", "2026-10-09T10:00:00+00:00"),  # after the run
    a_row("ingest-9", "z.pdf", "2026-10-05T09:00:00+00:00", quarter="2026Q1"),
]


def test_the_ingest_line_comes_from_the_last_ingest_before_the_run():
    line = ingest_line("2026Q2", ROWS, before="2026-10-06T00:00:00+00:00")

    assert line["did"] == "Fetched 2 files: 1 new, 1 unchanged"
    assert line["seconds"] == 2.5
    assert line["finished_at"] == "2026-10-05T10:00:02.500000+00:00"


def test_no_ingest_before_the_run_means_no_line():
    assert ingest_line("2026Q2", ROWS, before="2026-09-01T00:00:00+00:00") is None


def test_only_steps_that_wait_for_a_person_get_a_waiting_time():
    lines = [
        {"step": "extract", "seconds": 2.0, "finished_at": "2026-10-11T10:00:00+00:00"},
        {"step": "review", "seconds": 0.5, "finished_at": "2026-10-11T10:05:00+00:00"},
        {"step": "compute", "seconds": 1.0, "finished_at": "2026-10-11T10:05:01+00:00"},
    ]

    by_step = with_waits(lines, human_steps={"review"})

    assert by_step["review"]["waited"] == 299.5  # five minutes, less its own work
    assert by_step["extract"]["waited"] is None
    assert by_step["compute"]["waited"] is None


@pytest.mark.parametrize(
    ("seconds", "said"),
    [
        (0.12, "120 ms"),
        (4.25, "4.2 s"),
        (192, "3 min 12 s"),
        (7500, "2 h 5 min"),
        (100_000, "1 d 3 h"),
    ],
)
def test_durations_are_said_the_way_a_person_would(seconds, said):
    assert duration(seconds) == said
