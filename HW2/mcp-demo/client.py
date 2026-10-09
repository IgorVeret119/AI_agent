"""Small JSON-RPC stdio client with explicit metadata and bounded reads."""
import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

PROTOCOL = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL,
    "io.modelcontextprotocol/clientInfo": {"name": "schedule-demo", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


class WireClient:
    def __enter__(self):
        self.process = subprocess.Popen([sys.executable, str(Path(__file__).with_name("server.py"))], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.messages = queue.Queue()
        self.counter = 0
        self.trace = []
        threading.Thread(target=self._read, daemon=True).start()
        return self

    def _read(self):
        for line in self.process.stdout:
            self.messages.put(line)
        self.messages.put(None)

    def request(self, method, params=None):
        self.counter += 1
        request = {"jsonrpc": "2.0", "id": self.counter, "method": method, "params": {**(params or {}), "_meta": META}}
        self.trace.append({"request": request})
        self.process.stdin.write(json.dumps(request, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        while True:
            line = self.messages.get(timeout=20)
            if line is None:
                raise RuntimeError("Server exited without a response")
            response = json.loads(line)
            self.trace.append({"response": response})
            if response.get("id") == self.counter:
                if "error" in response:
                    raise RuntimeError(response["error"])
                return response["result"]

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def __exit__(self, *_):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.process.stdout.close()


def demo():
    with WireClient() as client:
        discovered = client.request("server/discover")
        assert PROTOCOL in discovered["supportedVersions"]
        catalog = client.request("tools/list")
        assert len(catalog["tools"]) == 4
        for name, args in (
            ("schedule_search", {"course": "agents"}),
            ("schedule_get", {"entry_id": "agents-mon"}),
            ("schedule_day", {"day": "wednesday"}),
            ("schedule_room", {"room": "314"}),
        ):
            success = client.call(name, {"schedule_handle": "schedule-v1", **args})
            assert not success.get("isError", False)
            failure = client.call(name, {"schedule_handle": "invalid", **args})
            assert failure["isError"]
        Path(__file__).with_name("artifacts").mkdir(exist_ok=True)
        Path(__file__).with_name("artifacts").joinpath("wire-log.json").write_text(json.dumps(client.trace, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"protocol": PROTOCOL, "transport": "stdio", "tools": [t["name"] for t in catalog["tools"]], "success_and_error_checked": True}


if __name__ == "__main__":
    print(json.dumps(demo(), ensure_ascii=False, indent=2))
