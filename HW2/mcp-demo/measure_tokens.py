"""Count actual serialized results using the named, reproducible encoding."""
import json
from pathlib import Path

import tiktoken

from client import WireClient

EXAMPLES = [
    ("schedule_search", {"course": "agents"}),
    ("schedule_get", {"entry_id": "agents-mon"}),
    ("schedule_day", {"day": "wednesday"}),
]


def measure():
    encoding = tiktoken.get_encoding("cl100k_base")
    rows = []
    with WireClient() as client:
        for name, args in EXAMPLES:
            row = {"tool": name, "arguments": {"schedule_handle": "schedule-v1", **args}}
            for mode in ("concise", "detailed"):
                answer = client.call(name, {**row["arguments"], "response_format": mode})
                assert not answer.get("isError", False)
                text = answer["content"][0]["text"]
                wire = json.dumps(answer, ensure_ascii=False, separators=(",", ":"))
                row[mode] = {"text_tokens": len(encoding.encode(text)), "result_tokens": len(encoding.encode(wire)), "text": text}
            rows.append(row)
    target = Path(__file__).with_name("artifacts")
    target.mkdir(exist_ok=True)
    report = {"encoding": "cl100k_base", "serialization": "UTF-8 JSON, ensure_ascii=False, compact separators", "examples": rows}
    (target / "token-counts.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("| Пример | concise: текст / результат | detailed: текст / результат |")
    print("| --- | ---: | ---: |")
    for row in rows:
        print(f"| `{row['tool']}` `{json.dumps(row['arguments'])}` | {row['concise']['text_tokens']} / {row['concise']['result_tokens']} | {row['detailed']['text_tokens']} / {row['detailed']['result_tokens']} |")


if __name__ == "__main__":
    measure()
