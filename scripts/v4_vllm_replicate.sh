#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
[[ "$(supervisorctl pid cacheflow_v3_sglang)" == 0 ]]
/venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --residency-events \
    --max-inflight 64 --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens 43664 --max-bypasses 8 --prepare-in-thread
bash scripts/v2_start.sh B2 fifo 6
/venv/main/bin/python - <<'PY'
import httpx
r=httpx.post('http://127.0.0.1:8000/v1/completions',timeout=120,
    json=dict(model='cacheflow-qwen3-4b',prompt='Hello',max_tokens=4,temperature=0))
r.raise_for_status()
PY
for seed in 101 102 103;do
    case "$seed" in
        101) arms=(fifo:16 fifo:64 lpm_real:16 bundle_wave:16 dhas:16 packing_reuse:64) ;;
        102) arms=(packing_reuse:64 dhas:16 bundle_wave:16 lpm_real:16 fifo:64 fifo:16) ;;
        103) arms=(lpm_real:16 packing_reuse:64 fifo:16 fifo:64 dhas:16 bundle_wave:16) ;;
    esac
    for arm in "${arms[@]}";do
        IFS=: read -r policy cap <<< "$arm"
        bash scripts/v3_gateway.sh "$cap" "$policy"
        bash scripts/v2_reset.sh
        bash scripts/v3_run.sh "v4-vllm-dev-${policy}${cap}-thread-qps4-s${seed}" \
            "data/processed/v3/v4-dev4b3-qps4-s${seed}.jsonl"
    done
done
supervisorctl stop cacheflow_v2_gateway cacheflow_v2_vllm cacheflow_v2_lmcache
