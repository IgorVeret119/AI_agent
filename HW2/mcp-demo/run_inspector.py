"""Run the real Inspector CLI, keeping commands, exit codes and output."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

CASES = [
    ("schedule_search", {"course": "agents"}),
    ("schedule_get", {"entry_id": "agents-mon"}),
    ("schedule_day", {"day": "wednesday"}),
    ("schedule_room", {"room": "314"}),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--node", default="node")
    parser.add_argument("--cli", required=True, help="Installed Inspector launcher JavaScript path")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    prefix = [args.node, args.cli, "--cli", sys.executable, str(root / "server.py"), "--", "--protocol-era", "modern", "--format", "json"]
    invocations = [("catalog", ["--method", "tools/list", "--strict"], False)]
    for name, arguments in CASES:
        for failure in (False, True):
            values = {"schedule_handle": "missing" if failure else "schedule-v1", **arguments, "response_format": "detailed"}
            flags = ["--method", "tools/call", "--tool-name", name, "--tool-args-json", json.dumps(values)]
            invocations.append((name + (" error" if failure else " success"), flags, failure))
    records = []
    for label, flags, failure in invocations:
        command = prefix + flags
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=60)
        record = {"case": label, "command": command, "exit_code": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}
        records.append(record)
        artifact_dir = root / "artifacts"
        artifact_dir.mkdir(exist_ok=True)
        (artifact_dir / "inspector-log.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        expected_code = 5 if failure else 0
        assert completed.returncode == expected_code, record
        assert "Traceback" not in completed.stderr, record
        envelope = json.loads(completed.stdout)
        if label != "catalog":
            assert envelope["result"].get("isError", False) == failure, record
        print(f"{label}: exit {completed.returncode}, verified")


if __name__ == "__main__":
    main()
