"""Download official Qwen GGUFs and a released llama.cpp Windows CPU runtime."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import requests


def get(url):
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    return response.json()


def download(url, path):
    temporary = path.with_suffix(path.suffix + ".partial")
    with requests.get(url, stream=True, timeout=(30, 180)) as response:
        response.raise_for_status()
        with temporary.open("wb") as stream:
            for chunk in response.iter_content(4 * 1024 * 1024):
                stream.write(chunk)
    temporary.replace(path)
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", required=True)
    args = parser.parse_args()
    root = Path(args.directory)
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"models": []}
    release = get("https://api.github.com/repos/ggml-org/llama.cpp/releases/latest")
    if any(a["name"] == "nightly-tag.txt" for a in release["assets"]):
        pointer = next(a for a in release["assets"] if a["name"] == "nightly-tag.txt")
        response = requests.get(pointer["browser_download_url"], timeout=60)
        response.raise_for_status()
        release = get("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/" + response.text.strip())
    assets = [a for a in release["assets"] if a["name"].endswith("bin-win-cpu-x64.zip")]
    if len(assets) != 1:
        raise RuntimeError("Cannot uniquely identify the released Windows CPU runtime")
    asset = assets[0]
    archive = root / asset["name"]
    digest = download(asset["browser_download_url"], archive)
    with zipfile.ZipFile(archive) as package:
        package.extractall(root / "llama")
    manifest["engine"] = {"tag": release["tag_name"], "url": asset["browser_download_url"], "sha256": digest}
    for role, repo in (("chat", "Qwen/Qwen3-0.6B-GGUF"), ("embedding", "Qwen/Qwen3-Embedding-0.6B-GGUF")):
        info = get("https://huggingface.co/api/models/" + repo)
        files = [f["rfilename"] for f in info["siblings"] if f["rfilename"].lower().endswith("q8_0.gguf")]
        if len(files) != 1:
            raise RuntimeError(f"Cannot identify Q8_0 file for {repo}: {files}")
        url = f"https://huggingface.co/{repo}/resolve/{info['sha']}/{files[0]}"
        target = root / Path(files[0]).name
        print(f"Downloading {role}: {repo} {files[0]}", flush=True)
        digest = download(url, target)
        manifest["models"].append({"role": role, "repo": repo, "revision": info["sha"], "file": files[0], "path": str(target.resolve()), "url": url, "sha256": digest, "quantization": "Q8_0"})
        (root / "model-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
