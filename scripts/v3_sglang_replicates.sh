#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for seed in 102 103; do
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
        "v3-sglang-lpm16-dev3-qps2-s${seed}" "data/processed/v3/dev3-qps2-s${seed}.jsonl"
done
