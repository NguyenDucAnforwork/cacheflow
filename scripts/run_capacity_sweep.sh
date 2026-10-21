#!/usr/bin/env bash
set -euo pipefail
cd /workspace
budget_file=/workspace/.cacheflow-gpu-kv-bytes
registry=results/raw/capacity_sweep_config.csv
trap 'rm -f "$budget_file"; supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache >/dev/null 2>&1 || true' EXIT
printf 'run_id,mode,gpu_kv_bytes,seed\n' > "$registry"
for spec in \
    '4 B1 b1-cap4-8k-r1' \
    '4 B2 b2-cap4-8k-r1' \
    '4 B2 b2-cap4-8k-r2' \
    '4 B1 b1-cap4-8k-r2' \
    '8 B2 b2-cap8-8k-r1' \
    '8 B1 b1-cap8-8k-r1' \
    '8 B1 b1-cap8-8k-r2' \
    '8 B2 b2-cap8-8k-r2'; do
    read -r gib mode run_id <<< "$spec"
    printf '%s\n' "$((gib * 1024 * 1024 * 1024))" > "$budget_file"
    bash scripts/set_mode.sh "$mode" fifo
    bash scripts/run_benchmark.sh "$run_id" long_doc_revisit 8192 8 4 64 7
    printf '%s,%s,%s,7\n' "$run_id" "$mode" "$((gib * 1024 * 1024 * 1024))" >> "$registry"
done
