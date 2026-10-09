import argparse
import hashlib
import json
import random
from pathlib import Path

from core import stable_seed, top_five, unit_vector
from local_api import LocalModels

ROOT = Path(__file__).resolve().parent
CHOICE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["tool"], "properties": {"tool": {"type": "string"}}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "results"))
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    tools = json.loads((ROOT / "data/tools.json").read_text(encoding="utf-8"))
    queries = json.loads((ROOT / "data/queries.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "data/dataset-manifest.json").read_text(encoding="utf-8"))
    api = LocalModels()
    cache_path = output / "embeddings.json"
    fingerprint = hashlib.sha256(json.dumps([tools, queries], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        assert cache["dataset_fingerprint"] == fingerprint, "Embedding cache belongs to different data"
    else:
        cache = {"dataset_fingerprint": fingerprint, "tools": {}, "queries": {}, "model": "Qwen/Qwen3-Embedding-0.6B", "pooling": "last", "query_instruction": "Given a user request, retrieve tool descriptions that can satisfy it."}
        for group, texts in (("tools", [(t["name"], t["description"]) for t in tools]), ("queries", [(q["id"], "Instruct: " + cache["query_instruction"] + "\nQuery: " + q["text"]) for q in queries])):
            for name, text in texts:
                vector, tokens, seconds = api.embed(text)
                cache[group][name] = {"vector": unit_vector(vector), "prompt_tokens": tokens, "seconds": seconds}
            print(f"Embedded {len(texts)} {group}", flush=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    vectors = {name: row["vector"] for name, row in cache["tools"].items()}
    retrieval = []
    for n in (5, 20, 50, 100):
        names = manifest["nested_pool_names"][str(n)]
        for query in queries:
            ranked = top_five(cache["queries"][query["id"]]["vector"], vectors, names)
            retrieval.append({"n": n, "query_id": query["id"], "gold": query["gold"], "top5": ranked, "hit": query["gold"] in ranked})
    (output / "retrieval.json").write_text(json.dumps(retrieval, ensure_ascii=False, indent=2), encoding="utf-8")
    retrieved = {(r["n"], r["query_id"]): r["top5"] for r in retrieval}
    path = output / "selection.jsonl"
    existing = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
    done = {(row["n"], row["variant"], row["repeat"], row["query_id"]) for row in existing}
    blocks = [(n, variant, repeat) for n in (5, 20, 50, 100) for variant in ("A", "B") for repeat in range(3)]
    random.Random(20261009).shuffle(blocks)
    descriptions = {t["name"]: t["description"] for t in tools}
    for n, variant, repeat in blocks:
        pool = list(manifest["nested_pool_names"][str(n)])
        random.Random(stable_seed("order", n, repeat)).shuffle(pool)
        ordered_queries = list(queries)
        random.Random(stable_seed("queries", n, variant, repeat)).shuffle(ordered_queries)
        for query in ordered_queries:
            key = (n, variant, repeat, query["id"])
            if key in done:
                continue
            allowed = set(pool if variant == "A" else retrieved[n, query["id"]])
            candidates = [name for name in pool if name in allowed]
            catalog = "\n".join(f"{name}: {descriptions[name]}" for name in candidates)
            messages = [{"role": "system", "content": "Select exactly one tool from the catalog for the user's request. Return only JSON {\"tool\":\"name\"}. " + manifest["routing_rule"] + "\nCatalog:\n" + catalog}, {"role": "user", "content": query["text"]}]
            response = api.chat(messages, CHOICE_SCHEMA, stable_seed("choice", n, repeat, query["id"]), max_tokens=48)
            predicted = response["parsed"].get("tool") if isinstance(response["parsed"], dict) else None
            row = {"n": n, "variant": variant, "repeat": repeat, "query_id": query["id"], "gold": query["gold"], "candidates": candidates, "predicted": predicted, "correct": predicted == query["gold"] and predicted in candidates, "query_embedding_tokens": cache["queries"][query["id"]]["prompt_tokens"] if variant == "B" else 0, **response}
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            done.add(key)
        print(f"N={n} {variant} repeat={repeat+1}; {len(done)}/720 choices saved", flush=True)


if __name__ == "__main__":
    main()
