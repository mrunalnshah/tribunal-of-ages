import json

import pytest

from tribunal.history import History, HistoryUnavailable


@pytest.fixture
def history(tmp_path):
    kept = History(f"sqlite:///{tmp_path}/history.db", max_chars=50)
    kept.setup()
    return kept


def test_every_grievance_is_kept_word_for_word_with_its_outcome(history, tmp_path):
    history.add("My roommate ate my pizza.", 3, ["ancient"], "verdict", "hammurabi-8", "rec1")
    history.add("Build me a Flutter app, please.", 2, ["fiction"], "contempt", "wonderland-rule-42")
    history.add("x" * 80, 4, ["ancient"], "too_long")
    path = tmp_path / "history.jsonl"
    assert history.export(path) == 3
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [entry["outcome"] for entry in entries] == ["verdict", "contempt", "too_long"]
    assert entries[0]["crime"] == "My roommate ate my pizza."
    assert entries[0]["themes"] == ["ancient"]
    assert entries[2]["length"] == 80 and len(entries[2]["crime"]) == 50  # kept up to the cap


def test_a_removal_link_deletes_the_entry_too(history, tmp_path):
    history.add("My roommate ate my pizza.", 3, ["ancient"], "verdict", "hammurabi-8", "rec1")
    assert history.forget("rec1") == 1
    assert history.export(tmp_path / "history.jsonl") == 0


def test_old_entries_can_be_pruned(history, tmp_path):
    history.add("My roommate ate my pizza.", 3, ["ancient"], "verdict")
    assert history.export(tmp_path / "recent.jsonl", days=1) == 1
    assert history.prune(0) == 1  # older than now: everything so far


def test_a_missing_database_closes_the_history_without_crashing(tmp_path):
    with pytest.raises(HistoryUnavailable):
        History(f"sqlite:///{tmp_path}/no/such/folder/history.db").setup()
