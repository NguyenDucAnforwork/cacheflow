"""Audit whether a bounded follower wait can reach producer readiness."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from cacheflow.analyze import percentile, read_jsonl


def diagnose(gateway_path: Path, run_id: str, max_wait_ms: int) -> dict:
    rows = [row for row in read_jsonl(gateway_path) if row.get("run_id") == run_id]
    candidates = [row for row in rows if row.get("delay_hit_candidate")]
    producer_ready_ms = []
    ready_within_bound = 0
    no_matching_producer = 0
    for follower in candidates:
        active_producers = [row for row in rows if row["request_id"] != follower["request_id"]
                            and row.get("prefix_group") == follower.get("prefix_group")
                            and row.get("dispatch_ns") is not None
                            and row["dispatch_ns"] <= follower["dispatch_ns"]
                            and (row.get("complete_ns") or 0) > follower["enqueue_ns"]]
        if not active_producers:
            no_matching_producer += 1
            continue
        producer = min(active_producers, key=lambda row: row["dispatch_ns"])
        if producer.get("first_token_ns") is None:
            continue
        delay = (producer["first_token_ns"] - follower["arrival_ns"]) / 1e6
        producer_ready_ms.append(delay)
        ready_within_bound += delay <= max_wait_ms
    waits = [row["queue_wait_ms"] for row in candidates if row.get("queue_wait_ms") is not None]
    bypassed = [row for row in candidates if row.get("readiness_guard_bypassed")]
    bypass_waits = [row["queue_wait_ms"] for row in bypassed if row.get("queue_wait_ms") is not None]
    estimates = [row["readiness_estimate_ms"] for row in bypassed
                 if isinstance(row.get("readiness_estimate_ms"), (int, float))]
    return {
        "run_id": run_id,
        "requests": len(rows),
        "delay_hit_candidates": len(candidates),
        "candidates_with_matching_producer": len(producer_ready_ms),
        "unresolved_producer_match": no_matching_producer,
        "producer_ready_within_wait_bound": ready_within_bound,
        "producer_ready_delay_p50_ms": percentile(producer_ready_ms, 50),
        "producer_ready_delay_p90_ms": percentile(producer_ready_ms, 90),
        "candidate_queue_wait_p50_ms": percentile(waits, 50),
        "candidate_queue_wait_mean_ms": statistics.mean(waits) if waits else None,
        "guard_bypassed_candidates": len(bypassed),
        "guard_bypassed_queue_wait_p50_ms": percentile(bypass_waits, 50),
        "guard_readiness_estimate_p50_ms": percentile(estimates, 50),
        "max_wait_ms": max_wait_ms,
        "note": "Matching uses logged prefix-group IDs and overlapping intervals; this is a scheduler feasibility audit, not proof of a cache hit.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gateway", type=Path)
    parser.add_argument("run_id")
    parser.add_argument("--max-wait-ms", type=int, default=200)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.gateway, args.run_id, args.max_wait_ms), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
