"""Deterministic metrics, paired fault injection, and a six-call guard."""
import datetime as dt
import hashlib
import json
import math
import random
import statistics
from collections import deque


def stable_seed(*parts):
    return int.from_bytes(hashlib.sha256(json.dumps(parts).encode()).digest()[:4], "big")


def normalized_call(name, arguments):
    return json.dumps({"name": name, "arguments": arguments}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def loop_reason(signatures):
    if len(signatures) >= 3 and signatures[-1] == signatures[-2] == signatures[-3]:
        return "three_identical"
    if len(signatures) >= 4 and signatures[-1] == signatures[-3] and signatures[-2] == signatures[-4] and signatures[-1] != signatures[-2]:
        return "alternating_abab"
    return None


class LoopGuard:
    """Provisional lecture substitute: block before completing either loop pattern."""
    def __init__(self, window=6):
        if window != 6:
            raise ValueError("This benchmark fixes the window at six")
        self.history = deque(maxlen=window)

    def before_call(self, name, arguments):
        signature = normalized_call(name, arguments)
        reason = loop_reason([*self.history, signature])
        if reason is None:
            self.history.append(signature)
        return reason


def unit_vector(values):
    norm = math.sqrt(sum(v * v for v in values))
    if not norm:
        raise ValueError("Zero embedding is not a usable semantic vector")
    return [v / norm for v in values]


def top_five(query_vector, tool_vectors, names):
    ranked = sorted(names, key=lambda name: (-sum(a * b for a, b in zip(query_vector, tool_vectors[name], strict=True)), name))
    return ranked[:5]


def percentile(values, fraction):
    values = sorted(values)
    position = (len(values) - 1) * fraction
    lo = math.floor(position)
    hi = math.ceil(position)
    return values[lo] + (values[hi] - values[lo]) * (position - lo)


def clustered_ci(groups, seed=20261009, draws=10000):
    """Groups are requests, each carrying all its repeats. Never sample rows."""
    scores = [statistics.mean(values) for _, values in sorted(groups.items())]
    if not scores:
        raise ValueError("No query clusters")
    rng = random.Random(seed)
    samples = [statistics.mean(rng.choices(scores, k=len(scores))) for _ in range(draws)]
    return [percentile(samples, 0.025), percentile(samples, 0.975)]


def fault_at(seed, ordinal):
    return random.Random(stable_seed("fault", seed, ordinal)).random() < 0.5


def schedule_search(arguments, fault_handle, explained, entries):
    """Unstable experimental version of schedule_search, with explicit fault state.

    fault_handle is harness metadata (seed, call ordinal), excluded from the
    domain call signature. There is no server session or process-global RNG.
    """
    seed, ordinal = map(int, fault_handle.split(":"))
    injected = fault_at(seed, ordinal)
    if arguments.get("schedule_handle") != "schedule-v1":
        return {"isError": True, "hint": "Use schedule_handle=schedule-v1."}, injected
    try:
        day = dt.date.fromisoformat(arguments["date"])
    except (KeyError, TypeError, ValueError):
        return {"isError": True, "hint": "Supply date in YYYY-MM-DD format."}, injected
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[day.weekday()]
    rows = [{**row, "date": day.isoformat()} for row in entries if row["day"] == weekday and row["course"] == arguments.get("course")]
    if injected or not rows:
        if explained:
            return {"entries": [], "message": "Ничего не найдено; попробуйте другое значение date в разрешённом интервале."}, injected
        return [], injected
    return {"entries": rows, "synthetic": True, "schedule_handle": "schedule-v1"}, injected


def successful_final(answer, observed, task):
    if not isinstance(answer, dict):
        return False
    return any(answer.get("entry_id") == row["id"] and answer.get("date") == row["date"] and row["course"] == task["course"] and task["start_date"] <= row["date"] <= task["end_date"] for row in observed)
