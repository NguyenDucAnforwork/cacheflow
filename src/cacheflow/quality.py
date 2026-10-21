"""Check paired replay identity and report output hash deviations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def read(path: Path) -> dict[str, dict]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line]
    by_id = {record["request_id"]: record for record in records}
    if len(records) != len(by_id):
        raise ValueError(f"duplicate request ID in {path}")
    return by_id


def compare(a_path: Path, b_path: Path) -> dict:
    a, b = read(a_path), read(b_path)
    if set(a) != set(b):
        raise ValueError("paired runs have different request IDs")
    matched = sorted(a)
    trace_hashes = {row["trace_sha256"] for row in [*a.values(), *b.values()]}
    if len(trace_hashes) != 1:
        raise ValueError("paired runs have different trace hashes")
    prompt_mismatches = [key for key in matched if a[key]["prompt_sha256"] != b[key]["prompt_sha256"] or a[key]["input_tokens"] != b[key]["input_tokens"]]
    status_errors = [key for key in matched if a[key]["status"] != "ok" or b[key]["status"] != "ok"]
    budget_mismatches = [key for key in matched if a[key]["output_tokens"] != b[key]["output_tokens"]]
    output_hash_mismatches = [key for key in matched if a[key]["output_hash"] != b[key]["output_hash"]]
    return {
        "a_run_id": next(iter(a.values()))["run_id"],
        "b_run_id": next(iter(b.values()))["run_id"],
        "trace_sha256": trace_hashes.pop(),
        "paired_requests": len(matched),
        "prompt_mismatch_ids": prompt_mismatches,
        "status_error_ids": status_errors,
        "output_token_count_mismatch_ids": budget_mismatches,
        "output_hash_mismatch_ids": output_hash_mismatches,
        "note": "Only SHA-256 hashes of generated text were stored; hash changes do not quantify semantic impact.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.a, args.b), indent=2))


if __name__ == "__main__":
    main()
