"""Only real llama.cpp HTTP responses; usage comes from the model server."""
import json
import time

import requests


class LocalModels:
    def __init__(self, chat_url="http://127.0.0.1:18080", embedding_url="http://127.0.0.1:18081"):
        self.chat_url = chat_url.rstrip("/")
        self.embedding_url = embedding_url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False

    def post(self, base, path, body):
        start = time.monotonic()
        response = self.session.post(base + path, json=body, timeout=(5, 180))
        response.raise_for_status()
        value = response.json()
        return value, time.monotonic() - start

    def embed(self, text):
        response, elapsed = self.post(self.embedding_url, "/v1/embeddings", {"model": "Qwen/Qwen3-Embedding-0.6B", "input": text, "encoding_format": "float"})
        return response["data"][0]["embedding"], response["usage"]["prompt_tokens"], elapsed

    def chat(self, messages, schema, seed, max_tokens=160):
        body = {"model": "Qwen/Qwen3-0.6B", "messages": messages, "temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0, "seed": seed, "max_tokens": max_tokens, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}, "response_format": {"type": "json_schema", "schema": schema}}
        response, elapsed = self.post(self.chat_url, "/v1/chat/completions", body)
        for field in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if field not in response["usage"]:
                raise RuntimeError("Model server did not report usage: " + field)
        content = response["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            parsed = None
        return {"parsed": parsed, "raw": response, "seconds": elapsed, "request": body}
