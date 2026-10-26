#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for seed in 101 102 103; do
    if [[ "$seed" == 102 ]]; then arms=(packing_fifo fifo); else arms=(fifo packing_fifo); fi
    for policy in "${arms[@]}"; do
        bash scripts/v3_gateway.sh 16 "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "v3-opt4b-${policy}16-lowreuse8-qps4-s${seed}" \
            "data/processed/v3/dev4b-lowreuse8-qps4-s${seed}.jsonl"
    done
done
for seed in 101 102 103; do
    bash scripts/v3_gateway.sh 16 residency
    bash scripts/v2_reset.sh
    bash scripts/v3_run.sh "v3-opt4b-residency16-dev3-qps4-s${seed}" \
        "data/processed/v3/dev4b3-qps4-s${seed}.jsonl"
done
