import pytest

from taxagent.cli import main


@pytest.mark.parametrize("bad", ["2026Q5", "Q2-2026", "2026", "26Q2"])
def test_invalid_quarter_is_rejected(bad):
    with pytest.raises(SystemExit) as exit_info:
        main(["ingest", "--quarter", bad])

    assert exit_info.value.code == 2  # argparse's "bad arguments" code


def test_quarter_is_required():
    with pytest.raises(SystemExit):
        main(["ingest"])
