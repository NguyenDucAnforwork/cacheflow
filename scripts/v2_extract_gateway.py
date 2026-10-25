"""Copy one completed run from the gateway's append-only JSONL trace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def extract(gateway_log: Path, request_log: Path, run_id: str, output: Path) -> int:
    requests = [json.loads(line) for line in request_log.read_text().splitlines() if line.strip()]
    expected = {row["request_id"] for row in requests}
    if not expected or len(expected) != len(requests):
        raise ValueError("request log is empty or has duplicate IDs")
    if not gateway_log.is_file():
        raise ValueError(f"gateway log missing: {gateway_log}")
    rows = [row for line in gateway_log.read_text().splitlines() if line.strip()
            if (row := json.loads(line)).get("run_id") == run_id]
    actual = [row["request_id"] for row in rows]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError(f"gateway/request ID mismatch: expected {len(expected)}, found {len(actual)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("".join(json.dumps(row, sort_keys=True) + "\n"
                              for row in sorted(rows, key=lambda item: item["request_id"])))
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-log", type=Path, required=True)
    parser.add_argument("--request-log", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(f"extracted {extract(args.gateway_log, args.request_log, args.run_id, args.output)} gateway rows")


if __name__ == "__main__":
    main()
