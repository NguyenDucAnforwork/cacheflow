"""Validate and compare one matched B2 FIFO / B3 DHAS E1 crossover."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _indexed(rows: list[dict], label: str) -> dict[str, dict]:
    indexed = {row["request_id"]: row for row in rows}
    if not indexed or len(indexed) != len(rows):
        raise ValueError(f"{label}: empty or duplicate request IDs")
    return indexed


def load_run(root: Path, run_id: str) -> dict:
    result_dir = root / "results/v2"
    if (result_dir / f"{run_id}.invalid").exists():
        raise ValueError(f"invalid marker exists for {run_id}")
    raw_dir = result_dir / "raw"
    summary = _json(raw_dir / f"{run_id}.summary.json")
    metrics = _json(result_dir / f"{run_id}.metrics_summary.json")
    requests = _indexed(_jsonl(raw_dir / f"{run_id}.jsonl"), "request log")
    gateway = _indexed(_jsonl(raw_dir / f"{run_id}.gateway.jsonl"), "gateway log")
    if summary["run_id"] != run_id or summary["requests"] != len(requests):
        raise ValueError(f"run summary mismatch: {run_id}")
    if summary["errors"] or summary["successes"] != len(requests):
        raise ValueError(f"run has failed requests: {run_id}")
    if requests.keys() != gateway.keys():
        raise ValueError(f"gateway IDs differ from request IDs: {run_id}")
    if any(row["status"] != "ok" for row in requests.values()):
        raise ValueError(f"request status is not ok: {run_id}")
    if any(row["status"] != "ok" for row in gateway.values()):
        raise ValueError(f"gateway status is not ok: {run_id}")
    for request_id, row in requests.items():
        if row["run_id"] != run_id or row["trace_sha256"] != summary["trace_sha256"]:
            raise ValueError(f"request provenance mismatch: {request_id}")
        if gateway[request_id]["run_id"] != run_id:
            raise ValueError(f"gateway provenance mismatch: {request_id}")
        if gateway[request_id]["input_tokens"] != row["input_tokens"]:
            raise ValueError(f"gateway token count differs from trace: {request_id}")
        reported = row.get("server_prompt_tokens")
        if reported is not None and reported != row["input_tokens"]:
            raise ValueError(f"server token count differs from trace: {row['request_id']}")
    return {"summary": summary, "metrics": metrics, "requests": requests, "gateway": gateway}


def _counter(run: dict, source: str, name: str) -> float | None:
    return run["metrics"]["counter_deltas"].get(source, {}).get(name)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def compare(b2: dict, b3: dict) -> dict:
    left, right = b2["summary"], b3["summary"]
    if (left["mode"], left["policy"]) != ("B2", "fifo"):
        raise ValueError("first arm must be B2 FIFO")
    if (right["mode"], right["policy"]) != ("B3", "dhas"):
        raise ValueError("second arm must be B3 DHAS")
    for key in ("trace_sha256", "model_revision", "model_name", "gpu_kv_bytes",
                "max_model_len", "output_tokens_budget", "source_sha256",
                "prompt_version", "protocol", "arrival", "vllm_version",
                "lmcache_version", "transformers_version"):
        if left.get(key) != right.get(key):
            raise ValueError(f"unmatched run metadata: {key}")
    for key in ("trace_sha256", "model_revision", "gpu_kv_bytes"):
        if left.get(key) is None:
            raise ValueError(f"required run metadata missing: {key}")
    for key in ("engine_pid", "lmcache_pid"):
        if not left.get(key) or left[key] != right.get(key):
            raise ValueError(f"serving process changed between arms: {key}")
    if b2["requests"].keys() != b3["requests"].keys():
        raise ValueError("request ID sets differ")
    for request_id, row in b2["requests"].items():
        if row["prompt_sha256"] != b3["requests"][request_id]["prompt_sha256"]:
            raise ValueError(f"prompt changed: {request_id}")
    paired = []
    for request_id in sorted(b2["requests"]):
        x, y = b2["requests"][request_id], b3["requests"][request_id]
        paired.append({
            "request_id": request_id,
            "b2_ttft_ms": x["arrival_ttft_ms"],
            "b3_ttft_ms": y["arrival_ttft_ms"],
            "delta_b3_minus_b2_ms": y["arrival_ttft_ms"] - x["arrival_ttft_ms"],
            "b2_admission_wait_ms": b2["gateway"][request_id]["admission_wait_ms"],
            "b3_admission_wait_ms": b3["gateway"][request_id]["admission_wait_ms"],
            "b3_delay_hit_candidate": b3["gateway"][request_id].get("delay_hit_candidate"),
        })
    counters = {
        "computed_prefill_tokens": ("vllm", "vllm:request_prefill_kv_computed_tokens_sum"),
        "prompt_tokens_cached": ("vllm", "vllm:prompt_tokens_cached_total"),
        "external_prefix_hits": ("vllm", "vllm:external_prefix_cache_hits_total"),
        "lmcache_chunks_loaded": ("lmcache", "lmcache_mp_num_chunks_loaded_total"),
    }
    counter_summary = {}
    for label, (source, name) in counters.items():
        x, y = _counter(b2, source, name), _counter(b3, source, name)
        counter_summary[label] = {"b2": x, "b3": y,
                                  "delta_b3_minus_b2": y - x if x is not None and y is not None else None}
    follower = [row["delta_b3_minus_b2_ms"] for row in paired
                if row["request_id"].endswith("-follower")]
    return {
        "b2_run_id": left["run_id"], "b3_run_id": right["run_id"],
        "trace_sha256": left["trace_sha256"],
        "engine_pid": left["engine_pid"], "lmcache_pid": left["lmcache_pid"],
        "requests": len(paired), "paired_requests": paired,
        "arrival_ttft_p50_ms": {"b2": left["arrival_ttft_p50_ms"],
                                "b3": right["arrival_ttft_p50_ms"]},
        "follower_ttft_delta_median_ms": _median(follower),
        "counter_deltas": counter_summary,
        "note": "Run-level pilot contrast only; inspect resets, cache state and replicates before causal claims.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--b2", required=True)
    parser.add_argument("--b3", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(load_run(args.root, args.b2), load_run(args.root, args.b3))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: result[key] for key in ("b2_run_id", "b3_run_id", "requests",
                                                  "follower_ttft_delta_median_ms", "counter_deltas")},
                     sort_keys=True))


if __name__ == "__main__":
    main()
