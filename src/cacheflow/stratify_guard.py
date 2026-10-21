"""Stratify a guarded-policy crossover by its logged admission decisions."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from .analyze import read_jsonl


def phase_ms(row: dict, start: str, end: str) -> float:
    return (row[end] - row[start]) / 1e6


def summarize(gateway_path: Path, baseline_id: str, guarded_id: str) -> dict:
    selected = [x for x in read_jsonl(gateway_path) if x.get("run_id") in {baseline_id, guarded_id} and x.get("status") == "ok"]
    baseline = {x["request_id"]: x for x in selected if x["run_id"] == baseline_id}
    guarded = {x["request_id"]: x for x in selected if x["run_id"] == guarded_id}
    if len(selected) != len(baseline) + len(guarded) or not baseline or set(baseline) != set(guarded):
        raise ValueError("missing or duplicate paired requests")
    if not guarded_id.startswith("b3g-"):
        raise ValueError("second run must use the guarded policy")
    groups = {
        "bypassed": [key for key, row in guarded.items() if row.get("readiness_guard_bypassed")],
        "other_candidate": [key for key, row in guarded.items() if row.get("delay_hit_candidate") and not row.get("readiness_guard_bypassed")],
        "noncandidate": [key for key, row in guarded.items() if not row.get("delay_hit_candidate")],
    }
    result = {"baseline_run_id": baseline_id, "guarded_run_id": guarded_id, "paired_count": len(baseline), "groups": {}}
    phase_defs = {
        "arrival_to_dispatch_ms": ("arrival_ns", "dispatch_ns"),
        "dispatch_to_first_ms": ("dispatch_ns", "first_token_ns"),
        "arrival_to_first_ms": ("arrival_ns", "first_token_ns"),
    }
    for label, keys in groups.items():
        item = {"count": len(keys)}
        for phase, (start, end) in phase_defs.items():
            deltas = [phase_ms(guarded[key], start, end) - phase_ms(baseline[key], start, end) for key in keys]
            item[phase + "_mean_delta"] = statistics.mean(deltas) if deltas else None
        result["groups"][label] = item
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("gateway", type=Path)
    parser.add_argument("baseline_run_id")
    parser.add_argument("guarded_run_id")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = summarize(args.gateway, args.baseline_run_id, args.guarded_run_id)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
