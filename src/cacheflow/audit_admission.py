"""Audit arrival-to-dispatch delays against the intentional wait bound."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from .analyze import percentile, read_jsonl


def summarize(config: dict[str, str], rows: list[dict], bound_ms: int) -> dict:
    run = config["run_id"]
    selected = [x for x in rows if x.get("run_id") == run]
    if not selected or any(x.get("queue_wait_ms") is None for x in selected):
        raise ValueError(f"missing gateway timings for {run}")
    waits = [x["queue_wait_ms"] for x in selected]
    overrun = [max(0.0, wait - bound_ms) for wait in waits]
    for x, expected in zip(selected, overrun):
        logged = x.get("admission_deadline_overrun_ms")
        if logged is not None and abs(logged - expected) > 0.01:
            raise ValueError(f"deadline overrun disagreement in {run}/{x['request_id']}")
    candidates = [x["queue_wait_ms"] for x in selected if x.get("delay_hit_candidate")]
    return {**config, "requests": len(selected), "errors": sum(x.get("status") != "ok" for x in selected),
            "delay_hit_candidates": len(candidates), "guard_bypasses": sum(bool(x.get("readiness_guard_bypassed")) for x in selected),
            "queue_wait_p50_ms": percentile(waits, 50), "queue_wait_p90_ms": percentile(waits, 90),
            "queue_wait_max_ms": max(waits), "over_bound_count": sum(x > 0 for x in overrun),
            "over_bound_p90_ms": percentile(overrun, 90), "over_bound_max_ms": max(overrun),
            "candidate_queue_wait_p50_ms": percentile(candidates, 50)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--gateway", type=Path, default=Path("results/raw/gateway.jsonl"))
    parser.add_argument("--bound-ms", type=int, default=200)
    parser.add_argument("--output", type=Path, default=Path("results/figures/admission_audit.csv"))
    args = parser.parse_args()
    with args.matrix.open(newline="") as stream:
        configs = list(csv.DictReader(stream))
    rows = read_jsonl(args.gateway)
    data = [summarize(config, rows, args.bound_ms) for config in configs]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
