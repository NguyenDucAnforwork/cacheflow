"""Prove CPU KV restore after clearing only vLLM's local GPU prefix cache."""

import json
import time

import httpx

VLLM = "http://127.0.0.1:8000"
LMCACHE = "http://127.0.0.1:18080"
NAMES = (
    "vllm:prefix_cache_hits_total",
    "vllm:external_prefix_cache_hits_total",
    "lmcache_mp_l1_read_chunks_total",
    "lmcache_mp_l1_write_chunks_total",
    "lmcache_mp_num_chunks_loaded_total",
)


def metrics(client):
    values = {}
    for url in (VLLM, LMCACHE):
        for line in client.get(url + "/metrics").text.splitlines():
            for name in NAMES:
                if line.startswith(name + "{") or line.startswith(name + " "):
                    values[name] = values.get(name, 0) + float(line.rsplit(" ", 1)[1])
    return values


def request(client, question):
    prefix = "This synthetic archive compares CPU and GPU cache transfers, latency, scheduling, and evidence. " * 180
    body = {"model": "cacheflow-qwen3-1.7b", "prompt": prefix + question,
            "max_tokens": 8, "temperature": 0, "add_special_tokens": False}
    response = client.post(VLLM + "/v1/completions", json=body)
    response.raise_for_status()
    return response.json()["usage"]


with httpx.Client(timeout=120) as client:
    first = request(client, " Question A: summarize. Answer:")
    time.sleep(2)
    reset = client.post(VLLM + "/reset_prefix_cache")
    reset.raise_for_status()
    before = metrics(client)
    second = request(client, " Question B: summarize. Answer:")
    after = metrics(client)
    delta = {name: after.get(name, 0) - before.get(name, 0) for name in NAMES}
    print(json.dumps({"first_usage": first, "second_usage": second, "reset_status": reset.status_code,
                      "metric_delta": delta, "cpu_restore_confirmed":
                      delta["vllm:external_prefix_cache_hits_total"] > 0 and
                      delta["lmcache_mp_l1_read_chunks_total"] > 0 and
                      delta["lmcache_mp_num_chunks_loaded_total"] > 0}, indent=2, sort_keys=True))
