"""Reproduce the full local benchmark; owned inference processes always stop."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent


def launch_script(name, output):
    bootstrap = f"import sys,runpy; sys.path.insert(0,{str(ROOT)!r}); sys.argv=[{name!r},'--output',{str(output)!r}]; runpy.run_path({str(ROOT / name)!r},run_name='__main__')"
    subprocess.run([sys.executable, "-c", bootstrap], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True, help="Directory populated by download_models.py")
    parser.add_argument("--output", default=str(ROOT / "results"))
    args = parser.parse_args()
    runtime, output = Path(args.runtime).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((runtime / "model-manifest.json").read_text(encoding="utf-8"))
    models = {m["role"]: m for m in manifest["models"]}
    binary = next((runtime / "llama").rglob("llama-server.exe"))
    processes, logs = [], []
    session = requests.Session()
    session.trust_env = False
    try:
        for role, port in (("chat", 18080), ("embedding", 18081)):
            try:
                session.get(f"http://127.0.0.1:{port}/health", timeout=1)
            except requests.ConnectionError:
                pass
            else:
                raise RuntimeError(f"Port {port} is occupied; stop the existing process or use the individual benchmark scripts.")
            command = [str(binary), "-m", models[role]["path"], "--alias", "Qwen/Qwen3-0.6B" if role == "chat" else "Qwen/Qwen3-Embedding-0.6B", "--host", "127.0.0.1", "--port", str(port), "-c", "8192" if role == "chat" else "2048", "-np", "1", "-t", "8", "-tb", "8"]
            command += ["--jinja"] if role == "chat" else ["-b", "2048", "-ub", "2048", "--embedding", "--pooling", "last"]
            log = (output / f"{role}-server.log").open("w", encoding="utf-8")
            logs.append(log)
            process = subprocess.Popen(command, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            processes.append(process)
            deadline = time.monotonic() + 60
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"{role} server exited: see log")
                try:
                    response = session.get(f"http://127.0.0.1:{port}/health", timeout=1)
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError(f"{role} server did not start")
                time.sleep(0.25)
        manifest_path = output / "model-manifest.json"
        if manifest_path.exists():
            assert json.loads(manifest_path.read_text(encoding="utf-8")) == manifest, "Resume requires identical model manifest"
        else:
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        for name in ("run_selection.py", "run_loops.py", "audit_results.py", "analyze.py"):
            launch_script(name, output)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
