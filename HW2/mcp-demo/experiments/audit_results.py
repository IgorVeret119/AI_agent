"""Recompute scores from raw actions and validate pairing and token accounting."""
import argparse
import json
from pathlib import Path

from core import fault_at, loop_reason, normalized_call, successful_final

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results"))
    args = parser.parse_args()
    root = Path(args.output)
    selection = [json.loads(line) for line in (root / "selection.jsonl").read_text(encoding="utf-8").splitlines()]
    loops = [json.loads(line) for line in (root / "loops.jsonl").read_text(encoding="utf-8").splitlines()]
    tasks = {t["id"]: t for t in json.loads((ROOT / "data/loop_tasks.json").read_text(encoding="utf-8"))}
    queries = {q["id"]: q for q in json.loads((ROOT / "data/queries.json").read_text(encoding="utf-8"))}
    pairs = {(r["n"], r["variant"], r["repeat"], r["query_id"]): r for r in selection}
    for row in selection:
        assert row["gold"] == queries[row["query_id"]]["gold"]
        assert row["correct"] == (row["predicted"] == row["gold"] and row["predicted"] in row["candidates"])
        assert len(row["candidates"]) == (row["n"] if row["variant"] == "A" else 5)
        usage = row["raw"]["usage"]
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
        assert row["raw"]["model"] == "Qwen/Qwen3-0.6B"
        if row["variant"] == "B":
            other = pairs[row["n"], "A", row["repeat"], row["query_id"]]
            assert row["request"]["seed"] == other["request"]["seed"]
            assert row["candidates"] == [name for name in other["candidates"] if name in row["candidates"]]
            if row["n"] == 5:
                assert row["request"] == other["request"]
    for row in loops:
        observed, signatures = [], []
        tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final = None
        for event in row["trace"]:
            for key in tokens:
                tokens[key] += event["raw"]["usage"][key]
            if isinstance(event["parsed"], dict) and "final" in event["parsed"]:
                final = event["parsed"]["final"]
            if "tool_result" in event:
                action = event["parsed"]
                signatures.append(normalized_call(action["tool"], action["arguments"]))
                seed, ordinal = map(int, event["fault_handle"].split(":"))
                assert seed == row["fault_seed"] and ordinal == len(signatures)
                assert event["fault_injected"] == fault_at(seed, ordinal)
                if event["fault_injected"]:
                    assert event["tool_result"] == [] if row["variant"] != "hint" else event["tool_result"]["entries"] == []
                if isinstance(event["tool_result"], dict):
                    observed.extend(event["tool_result"].get("entries", []))
        assert row["usage"] == tokens
        assert row["steps"] == len(row["trace"]) <= 12
        assert row["success"] == successful_final(final, observed, tasks[row["task_id"]])
        assert row["loop"] == any(loop_reason(signatures[:i]) for i in range(1, len(signatures) + 1))
        if row["variant"] == "guard":
            assert not row["loop"]
    assert len(selection) == len(pairs) == 720 and len(loops) == 180
    report = {"selection_rows_verified": len(selection), "episodes_verified": len(loops), "checks": ["gold_labels", "recomputed_accuracy", "candidate_count", "paired_seeds_and_order", "N5_identical_requests", "token_usage_sum", "fault_masks", "observed_success", "loop_definitions", "guard_prevents_execution"]}
    (root / "audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
