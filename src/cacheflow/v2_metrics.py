"""Summarize before/after serving counters for one V2 replay."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

COUNTERS = {
    "vllm": (
        "vllm:prefix_cache_hits_total",
        "vllm:external_prefix_cache_hits_total",
        "vllm:prompt_tokens_total",
        "vllm:prompt_tokens_cached_total",
        "vllm:request_prefill_kv_computed_tokens_sum",
        "vllm:request_queue_time_seconds_sum",
    ),
    "lmcache": (
        "lmcache_mp_l1_read_chunks_total",
        "lmcache_mp_l1_write_chunks_total",
        "lmcache_mp_l1_evicted_chunks_total",
        "lmcache_mp_num_chunks_loaded_total",
    ),
}


def summarize(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if len(rows) < 2:
        raise ValueError("need at least two metric samples")
    if rows[-1]["timestamp_ns"] <= rows[0]["timestamp_ns"]:
        raise ValueError("metric timestamps are not increasing")
    deltas: dict[str, dict[str, float | None]] = {}
    for source, names in COUNTERS.items():
        first = rows[0].get(source, {})
        last = rows[-1].get(source, {})
        values = {}
        for name in names:
            if name not in first or name not in last:
                values[name] = None
                continue
            value = last[name] - first[name]
            if value < 0:
                raise ValueError(f"counter reset during replay: {name}")
            values[name] = value
        deltas[source] = values
    vram = [row.get("gpu", {}).get("vram_used_mib") for row in rows]
    available = [row.get("memory_available_bytes") for row in rows]
    return {
        "metrics_path": str(path),
        "samples": len(rows),
        "first_timestamp_ns": rows[0]["timestamp_ns"],
        "last_timestamp_ns": rows[-1]["timestamp_ns"],
        "duration_s": (rows[-1]["timestamp_ns"] - rows[0]["timestamp_ns"]) / 1e9,
        "vram_peak_mib": max((x for x in vram if x is not None), default=None),
        "host_memory_available_min_bytes": min((x for x in available if x is not None), default=None),
        "counter_deltas": deltas,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("metrics_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.metrics_path)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
