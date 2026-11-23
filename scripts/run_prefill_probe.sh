#!/usr/bin/env bash
# usage: run_prefill_probe.sh MNBT ... (e.g. 2048 8192 4096 8192 2048); B1 (GPU prefix cache only), cold restart per entry.
set -euo pipefail
cd /workspace
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home PYTHONPATH=/workspace/src
n=0
for mnbt in "$@"; do
    n=$((n + 1))
    label="mnbt${mnbt}-s${n}"
    printf '%s\n' "$mnbt" > /workspace/.cacheflow-mnbt
    echo "### $label start $(date +%T)"
    bash scripts/set_mode.sh B1 fifo > "/workspace/results/raw/probe-${label}.setmode.log" 2>&1
    python -m cacheflow.prefill_probe --trace-file /workspace/data/traces/real60_burst.jsonl \
        --label "$label" --output "/workspace/results/raw/probe-${label}.jsonl"
done
supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache >/dev/null 2>&1 || true
rm -f /workspace/.cacheflow-mnbt
