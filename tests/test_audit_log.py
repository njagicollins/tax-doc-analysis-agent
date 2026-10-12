import json

from taxagent.audit.log import FIRST, append_event, read_entries, verify


def three_events(path):
    append_event("run_started", "system", {"run_id": "2026Q2-x"}, path)
    append_event("review_submitted", "alice", {"values": 6}, path)
    return append_event("signed_off", "bob", {"approve": True}, path)


def rewrite(path, change):
    """Tamper with the file behind the log's back."""
    entries = read_entries(path)
    change(entries)
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def test_each_entry_points_at_the_one_before(tmp_path):
    path = tmp_path / "audit.jsonl"
    three_events(path)

    first, second, third = read_entries(path)

    assert [e["seq"] for e in (first, second, third)] == [1, 2, 3]
    assert first["prev_hash"] == FIRST
    assert second["prev_hash"] == first["hash"]
    assert third["prev_hash"] == second["hash"]


def test_an_untouched_log_has_no_problems(tmp_path):
    path = tmp_path / "audit.jsonl"
    three_events(path)

    assert verify(path) == []


def test_an_empty_log_has_no_problems(tmp_path):
    assert verify(tmp_path / "audit.jsonl") == []


def test_a_changed_entry_is_found(tmp_path):
    path = tmp_path / "audit.jsonl"
    three_events(path)

    def approve_becomes_reject(entries):
        entries[2]["details"]["approve"] = False

    rewrite(path, approve_becomes_reject)

    assert verify(path) == ["entry 3 was changed after it was written"]


def test_a_removed_entry_is_found(tmp_path):
    path = tmp_path / "audit.jsonl"
    three_events(path)

    rewrite(path, lambda entries: entries.pop(1))  # alice's review disappears

    assert "entry 2 does not follow the entry before it" in verify(path)


def test_entries_in_the_wrong_order_are_found(tmp_path):
    path = tmp_path / "audit.jsonl"
    three_events(path)

    rewrite(path, lambda entries: entries.reverse())

    assert verify(path) != []


def test_cutting_off_the_end_needs_an_outside_copy_to_be_found(tmp_path):
    path = tmp_path / "audit.jsonl"
    last = three_events(path)

    rewrite(path, lambda entries: entries.pop())  # bob's sign-off disappears

    assert verify(path) == []  # the limit: what is left is still a valid chain
    assert verify(path, last_hash=last["hash"]) == [
        "the log does not end where the outside copy says it should"
    ]
