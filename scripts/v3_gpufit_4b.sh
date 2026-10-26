#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
for ((i=0;i<240;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null; then break; fi
    sleep 2
done
curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null
for seed in 101 102 103; do
    if [[ "$seed" == 102 ]]; then arms=(packing_fifo fifo); else arms=(fifo packing_fifo); fi
    for policy in "${arms[@]}"; do
        bash scripts/v3_gateway.sh 16 "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "v3-gpufit4b-${policy}16-dev3-qps4-s${seed}" \
            "data/processed/v3/dev4b3-qps4-s${seed}.jsonl"
    done
done
