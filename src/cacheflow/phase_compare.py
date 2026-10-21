"""Matched gateway phase decomposition for two fixed-arrival runs."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from cacheflow.analyze import percentile, read_jsonl


def phases(row: dict) -> dict[str, float]:
    arrival = row["arrival_ns"]
    dispatch = row["dispatch_ns"]
    first = row["first_token_ns"]
    complete = row["complete_ns"]
    return {
        "arrival_to_dispatch_ms": (dispatch - arrival) / 1e6,
        "dispatch_to_first_ms": (first - dispatch) / 1e6,
        "arrival_to_first_ms": (first - arrival) / 1e6,
        "first_to_complete_ms": (complete - first) / 1e6,
    }


def compare(gateway_path: Path, a_run: str, b_run: str) -> dict:
    records = read_jsonl(gateway_path)
    a = {r["request_id"]: r for r in records if r.get("run_id") == a_run and r.get("status") == "ok"}
    b = {r["request_id"]: r for r in records if r.get("run_id") == b_run and r.get("status") == "ok"}
    if not a or set(a) != set(b):
        raise ValueError("successful request IDs differ or are absent")
    result = {"a_run_id": a_run, "b_run_id": b_run, "paired_count": len(a),
              "a_delay_hit_candidates": sum(bool(r.get("delay_hit_candidate")) for r in a.values()),
              "b_delay_hit_candidates": sum(bool(r.get("delay_hit_candidate")) for r in b.values())}
    for name in phases(next(iter(a.values()))):
        aa = [phases(a[key])[name] for key in sorted(a)]
        bb = [phases(b[key])[name] for key in sorted(a)]
        delta = [y - x for x, y in zip(aa, bb)]
        result[name] = {
            "a_mean_ms": statistics.mean(aa), "b_mean_ms": statistics.mean(bb),
            "paired_mean_delta_ms": statistics.mean(delta),
            "paired_median_delta_ms": percentile(delta, 50),
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gateway", type=Path)
    parser.add_argument("a_run")
    parser.add_argument("b_run")
    args = parser.parse_args()
    print(json.dumps(compare(args.gateway, args.a_run, args.b_run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
