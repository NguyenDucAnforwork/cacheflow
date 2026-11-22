#!/usr/bin/env bash
# usage: run_real_benchmark.sh RUN_ID TRACE_NAME   (env: REGISTRY, default /workspace/results/real_registry.csv)
set -euo pipefail
run_id=${1:?usage: run_real_benchmark.sh RUN_ID TRACE_NAME}
trace=${2:?missing trace name}
registry=${REGISTRY:-/workspace/results/real_registry.csv}
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home PYTHONPATH=/workspace/src
model=/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e
out="/workspace/results/raw/${run_id}.jsonl"
metrics_out="${out%.jsonl}.metrics.jsonl"
python -m cacheflow.collect_metrics --output "$metrics_out" &
collector=$!
trap 'kill -TERM "$collector" 2>/dev/null || true; wait "$collector" 2>/dev/null || true' EXIT
for _ in $(seq 1 100); do
    [[ -s "$metrics_out" ]] && break
    kill -0 "$collector" 2>/dev/null || { echo 'Metrics collector exited before first sample' >&2; exit 1; }
    sleep 0.1
done
[[ -s "$metrics_out" ]] || { echo 'Metrics collector produced no baseline sample' >&2; exit 1; }
python -m cacheflow.bench --url http://127.0.0.1:8100 --model-path "$model" \
    --workload real_quality_chat --trace-file "/workspace/data/traces/${trace}.jsonl" \
    --run-id "$run_id" --output "$out" --registry "$registry"
sleep 2  # capture final cache counters after the last response
