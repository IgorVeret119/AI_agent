import argparse
import json
import queue
import random
import subprocess
import sys
import threading
from pathlib import Path

from core import LoopGuard, fault_at, loop_reason, normalized_call, stable_seed, successful_final
from local_api import LocalModels

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from client import WireClient

DOMAIN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["schedule_handle", "course", "date"], "properties": {"schedule_handle": {"type": "string", "enum": ["schedule-v1"], "description": "Explicit schedule snapshot."}, "course": {"type": "string", "enum": ["agents", "python", "databases"], "description": "Requested course."}, "date": {"type": "string", "description": "Calendar date YYYY-MM-DD."}}}
ACTION_SCHEMA = {"anyOf": [
    {"type": "object", "additionalProperties": False, "required": ["tool", "arguments"], "properties": {"tool": {"type": "string", "enum": ["schedule_search"]}, "arguments": DOMAIN_SCHEMA}},
    {"type": "object", "additionalProperties": False, "required": ["final"], "properties": {"final": {"type": "object", "additionalProperties": False, "required": ["entry_id", "date"], "properties": {"entry_id": {"type": "string"}, "date": {"type": "string"}}}}},
]}


class ExperimentWire(WireClient):
    def __enter__(self):
        # Embedded Python omits the script directory from sys.path; runpy fixes it.
        root = str(ROOT)
        bootstrap = f"import sys,runpy; sys.path.insert(0,{root!r}); runpy.run_path({str(ROOT / 'unstable_server.py')!r},run_name='__main__')"
        self.process = subprocess.Popen([sys.executable, "-c", bootstrap], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.messages = queue.Queue()
        self.counter = 0
        self.trace = []
        threading.Thread(target=self._read, daemon=True).start()
        return self


def episode(api, wire, task, repeat, variant, max_steps=12):
    seed = stable_seed("episode", task["id"], repeat)
    guard = LoopGuard(window=6) if variant == "guard" else None
    messages = [{"role": "system", "content": "You solve course schedule tasks using a tool. At each step return only one JSON action: {\"tool\":\"schedule_search\",\"arguments\":{\"schedule_handle\":\"schedule-v1\",\"course\":\"agents\",\"date\":\"YYYY-MM-DD\"}}, or a final JSON {\"final\":{\"entry_id\":\"observed id\",\"date\":\"observed date\"}}. Tool: schedule_search — search the synthetic course schedule by course and calendar date. Use the user's requested course and allowed date interval. You may call the tool again when needed. A final answer must cite an entry actually returned by the tool. Never invent entries."}, {"role": "user", "content": task["text"]}]
    trace, signatures, observed = [], [], []
    success = False
    guarded = None
    status = "step_limit"
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    ordinal = 0
    for step in range(max_steps):
        response = api.chat(messages, ACTION_SCHEMA, stable_seed("agent", seed, step), max_tokens=160)
        for key in usage:
            usage[key] += response["raw"]["usage"][key]
        action = response["parsed"]
        event = {"step": step + 1, **response}
        trace.append(event)
        if not isinstance(action, dict):
            status = "invalid_json"
            break
        if "final" in action:
            success = successful_final(action["final"], observed, task)
            status = "success" if success else "unsupported_final"
            break
        name, arguments = action.get("tool"), action.get("arguments")
        if name != "schedule_search" or not isinstance(arguments, dict):
            status = "invalid_call"
            break
        messages.append({"role": "assistant", "content": response["raw"]["choices"][0]["message"]["content"]})
        if guard:
            guarded = guard.before_call(name, arguments)
            if guarded:
                event["guard_blocked"] = guarded
                status = "guard_stop"
                break
        signatures.append(normalized_call(name, arguments))
        ordinal += 1
        fault_handle = f"{seed}:{ordinal}"
        result = wire.call(name, {**arguments, "fault_handle": fault_handle, "response_mode": "hint" if variant == "hint" else "empty"})
        payload = json.loads(result["content"][0]["text"])
        event.update(tool_result=payload, fault_handle=fault_handle, fault_injected=fault_at(seed, ordinal))
        if isinstance(payload, dict) and "entries" in payload:
            observed.extend(payload["entries"])
        messages.append({"role": "user", "content": "Tool result: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))})
    has_loop = any(loop_reason(signatures[:i]) is not None for i in range(1, len(signatures) + 1))
    return {"task_id": task["id"], "repeat": repeat, "variant": variant, "fault_seed": seed, "success": success, "status": status, "loop": has_loop, "loop_attempt_or_execution": bool(has_loop or guarded), "guard_reason": guarded, "steps": len(trace), "executed_calls": len(signatures), "usage": usage, "trace": trace}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results"))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "loops.jsonl"
    tasks = json.loads((ROOT / "data/loop_tasks.json").read_text(encoding="utf-8"))
    existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    done = {(r["task_id"], r["repeat"], r["variant"]) for r in existing}
    jobs = [(task, repeat, variant) for task in tasks for repeat in range(3) for variant in ("baseline", "guard", "hint")]
    random.Random(20261009).shuffle(jobs)
    api = LocalModels()
    with ExperimentWire() as wire:
        wire.request("server/discover")
        for task, repeat, variant in jobs:
            key = (task["id"], repeat, variant)
            if key in done:
                continue
            row = episode(api, wire, task, repeat, variant)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            done.add(key)
            if len(done) % 10 == 0:
                print(f"{len(done)}/180 episodes saved", flush=True)
        (output / "loop-mcp-wire.json").write_text(json.dumps(wire.trace, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
