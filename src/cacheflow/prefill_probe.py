"""Isolated prefill timing: one real document at a time, no queue, no prefix-cache hit.

Purpose: test whether a larger max_num_batched_tokens shortens prefill because fewer scheduler steps are needed
(per-step overhead) rather than because of anything related to queueing. Requests go straight to vLLM (port 8000),
sequentially, with max_tokens=1. A unique nonce is prepended to every prompt so the prefix cache cannot hit.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from .bench import _engine_info
from .real_workload import load_trace


def one(client: httpx.Client, url: str, model: str, prompt: str) -> dict:
    body = {"model": model, "prompt": prompt, "max_tokens": 1, "temperature": 0, "stream": True,
            "add_special_tokens": False, "stream_options": {"include_usage": True}}
    start = time.perf_counter()
    first = None
    usage = None
    with client.stream("POST", url + "/v1/completions", json=body) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            if event.get("usage"):
                usage = event["usage"]
            if first is None and any(c.get("text") for c in event.get("choices", [])):
                first = time.perf_counter()
    end = time.perf_counter()
    return {"ttft_ms": (first - start) * 1e3 if first else None, "total_ms": (end - start) * 1e3,
            "prompt_tokens": usage["prompt_tokens"] if usage else None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace-file", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--model-name", default="cacheflow-qwen3-1.7b")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    rows, _ = load_trace(args.trace_file)
    docs = [r for r in rows if r.cls == "doc" and r.request_id.endswith("-q0")]
    engine = _engine_info()
    out = []
    with httpx.Client(timeout=httpx.Timeout(120)) as client:
        # untimed warm-up with a document-sized prompt so first-use costs are not counted
        one(client, args.url, args.model_name, f"[warmup {args.label}] " + docs[0].prompt)
        for k in range(args.passes):
            order = list(range(len(docs)))
            order = order[k % len(order):] + order[:k % len(order)]  # rotate so no document is always first
            for i in order:
                doc = docs[i]
                result = one(client, args.url, args.model_name, f"[probe {args.label} pass {k} doc {i}] " + doc.prompt)
                out.append({"label": args.label, "pass": k, "doc": doc.request_id, **result})
                time.sleep(0.3)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text("\n".join(json.dumps({**r, **engine}, sort_keys=True) for r in out) + "\n")
    print(args.label, len(out), "samples; engine", engine)


if __name__ == "__main__":
    main()
