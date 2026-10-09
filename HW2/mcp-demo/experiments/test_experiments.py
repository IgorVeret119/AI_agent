import json
from pathlib import Path

import pytest

from core import LoopGuard, clustered_ci, fault_at, loop_reason, normalized_call, schedule_search, successful_final, top_five

ROOT = Path(__file__).resolve().parent


def test_dataset_gold_present_and_sizes():
    tools = json.loads((ROOT / "data/tools.json").read_text(encoding="utf-8"))
    queries = json.loads((ROOT / "data/queries.json").read_text(encoding="utf-8"))
    assert len(tools) == 100 and len({t["name"] for t in tools}) == 100
    assert sum(t["near"] for t in tools) == 28
    assert len(queries) == 30
    for n in (5, 20, 50, 100):
        assert all(q["gold"] in {t["name"] for t in tools[:n]} for q in queries)


@pytest.mark.parametrize("calls,expected", [(["a", "a", "a"], "three_identical"), (["a", "b", "a", "b"], "alternating_abab"), (["a", "a"], None), (["a", "b", "a", "c"], None), (["a", "b", "c", "a"], None)])
def test_loop_definition(calls, expected):
    assert loop_reason(calls) == expected


def test_guard_blocks_before_loop_and_window_six():
    guard = LoopGuard()
    assert guard.before_call("schedule_search", {"date": "2026-10-12"}) is None
    assert guard.before_call("schedule_search", {"date": "2026-10-12"}) is None
    assert guard.before_call("schedule_search", {"date": "2026-10-12"}) == "three_identical"
    assert len(guard.history) == 2
    other = LoopGuard()
    for day in ("12", "13", "12"):
        assert other.before_call("schedule_search", {"date": day}) is None
    assert other.before_call("schedule_search", {"date": "13"}) == "alternating_abab"
    for i in range(20):
        guard.before_call("schedule_search", {"date": str(i)})
    assert len(guard.history) == 6


def test_argument_order_is_not_new_call():
    assert normalized_call("x", {"date": "a", "course": "b"}) == normalized_call("x", {"course": "b", "date": "a"})
    assert normalized_call("x", {"date": "a"}) != normalized_call("x", {"date": "b"})


def test_bootstrap_resamples_requests_not_repeats():
    # Two perfectly correlated clusters must have endpoint 0 and 1. Sampling
    # their 6 individual rows would falsely narrow the interval.
    assert clustered_ci({"q1": [0, 0, 0], "q2": [1, 1, 1]}, draws=2000) == [0.0, 1.0]
    assert clustered_ci({"q1": [1, 1, 1], "q2": [1, 1, 1]}, draws=100) == [1, 1]


def test_retrieval_cannot_see_tools_outside_pool():
    assert top_five([1, 0], {"a": [1, 0], "b": [0, 1], "outside": [1, 0]}, ["a", "b"]) == ["a", "b"]


def test_fault_pairing_probability_and_hint_only_changes_empty_response():
    entries = [{"id": "agents-mon", "course": "agents", "day": "monday"}]
    arguments = {"schedule_handle": "schedule-v1", "course": "agents", "date": "2026-10-12"}
    faults = []
    for ordinal in range(1, 1001):
        empty, fail_a = schedule_search(arguments, f"42:{ordinal}", False, entries)
        hint, fail_b = schedule_search(arguments, f"42:{ordinal}", True, entries)
        assert fail_a == fail_b == fault_at(42, ordinal)
        if fail_a:
            assert empty == [] and hint["entries"] == [] and "date" in hint["message"]
        else:
            assert empty == hint
        faults.append(fail_a)
    assert 0.45 < sum(faults) / len(faults) < 0.55


def test_success_requires_observed_course_and_in_range():
    task = {"course": "agents", "start_date": "2026-10-12", "end_date": "2026-10-19"}
    observed = [{"id": "agents-mon", "date": "2026-10-12", "course": "agents"}]
    assert successful_final({"entry_id": "agents-mon", "date": "2026-10-12"}, observed, task)
    assert not successful_final({"entry_id": "invented", "date": "2026-10-12"}, observed, task)
    assert not successful_final({"entry_id": "agents-mon", "date": "2026-10-20"}, observed, task)
