#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for seed in 101 102 103; do
    case "$seed" in
        101) arms=(fifo packing packing_reuse) ;;
        102) arms=(packing_reuse packing fifo native) ;;
        103) arms=(fifo native packing_reuse packing) ;;
    esac
    for arm in "${arms[@]}"; do
        id="v4-sg4b-fi-kernel-${arm}16-dev3-qps4-s${seed}"
        extra=()
        if [[ "$arm" == native ]]; then
            id="v4-sg4b-fi-kernel-lpm16-dev3-qps4-s${seed}"
        else
            bash scripts/v3_gateway.sh 16 "$arm"
            extra=(--replay-url http://127.0.0.1:8100 --gateway-policy "$arm")
        fi
        PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
            "$id" "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl" "${extra[@]}"
    done
done
