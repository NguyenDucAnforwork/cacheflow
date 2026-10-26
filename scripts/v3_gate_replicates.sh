#!/usr/bin/env bash
# Replicate observed ordering opportunity before designing an adaptive method.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for seed in 102 103; do
    if [[ "$seed" == 102 ]]; then arms=(lpm_hint fifo); else arms=(fifo lpm_hint); fi
    for policy in "${arms[@]}"; do
        id="v3-screen-${policy}4-dev3-qps2-s${seed}"
        echo "$(date -u +%FT%TZ) START $id"
        bash scripts/v3_gateway.sh 4 "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "$id" "data/processed/v3/dev3-qps2-s${seed}.jsonl"
        echo "$(date -u +%FT%TZ) DONE $id"
    done
done
