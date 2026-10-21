#!/usr/bin/env bash
set -euo pipefail
cd /workspace
budget_file=/workspace/.cacheflow-gpu-kv-bytes
registry=results/raw/workingset_12doc_config.csv
trap 'rm -f "$budget_file"; supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache >/dev/null 2>&1 || true' EXIT
printf '%s\n' 8589934592 > "$budget_file"
printf 'run_id,mode,gpu_kv_bytes,groups,per_group,seed\n' > "$registry"
for spec in \
    'B1 b1-ws12-cap8-r1' \
    'B2 b2-ws12-cap8-r1' \
    'B2 b2-ws12-cap8-r2' \
    'B1 b1-ws12-cap8-r2'; do
    read -r mode run_id <<< "$spec"
    bash scripts/set_mode.sh "$mode" fifo
    bash scripts/run_benchmark.sh "$run_id" long_doc_revisit 8192 12 4 64 7
    printf '%s,%s,8589934592,12,4,7\n' "$run_id" "$mode" >> "$registry"
done
