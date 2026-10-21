#!/usr/bin/env bash
set -euo pipefail
run_id=${1:?usage: run_benchmark.sh RUN_ID WORKLOAD [INPUT_TOKENS] [GROUPS] [PER_GROUP] [OUTPUT_TOKENS]}
workload=${2:?missing workload}
input_tokens=${3:-4096}
groups=${4:-8}
per_group=${5:-4}
output_tokens=${6:-64}
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home
export PYTHONPATH=/workspace/src
model=/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
out="/workspace/results/raw/${run_id}.jsonl"

python -m cacheflow.collect_metrics --output "${out%.jsonl}.metrics.jsonl" &
collector=$!
trap 'kill -TERM "$collector" 2>/dev/null || true; wait "$collector" 2>/dev/null || true' EXIT
python -m cacheflow.bench --url http://127.0.0.1:8100 --model-path "$model" \
    --workload "$workload" --input-tokens "$input_tokens" --groups "$groups" \
    --per-group "$per_group" --output-tokens "$output_tokens" \
    --run-id "$run_id" --output "$out"
sleep 2  # capture final cache counters after the last response
