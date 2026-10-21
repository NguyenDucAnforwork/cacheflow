"""Cold/warm completion probe. Prints metadata, never prompt content."""

import hashlib
import json
import sys

import httpx

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
model = "cacheflow-qwen3-1.7b"
prefix = ("This synthetic archive compares CPU and GPU cache transfers, latency, scheduling, and evidence. " * 180)
with httpx.Client(timeout=120) as client:
    for i in range(2):
        payload = {"model": model, "prompt": prefix + f" Question {i}: describe the archive. Answer:",
                   "max_tokens": 8, "temperature": 0, "add_special_tokens": False}
        response = client.post(url.rstrip("/") + "/v1/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["text"]
        print(json.dumps({"request": i, "usage": data.get("usage"),
                          "output_sha256": hashlib.sha256(text.encode()).hexdigest()}))
    metrics = client.get(url.rstrip("/") + "/metrics").text
    for line in metrics.splitlines():
        if line.startswith(("vllm:prefix_cache_hits", "vllm:prompt_tokens_cached_by_source", "vllm:request_prefill_kv_computed_tokens")):
            print(line[:250])
