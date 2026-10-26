#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend kernel --max-running-requests 16 \
    --inbatch-check-threshold 1024 --inbatch-deprioritize-threshold 1024
supervisorctl start cacheflow_v3_sglang
for ((i=0;i<180;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null; then break;fi
    sleep 2
done
for phase in warm measured; do
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
        "v4-sg-inbatch1024-native-${phase}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl
done
/venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 16 \
    --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens 43664 --upstream http://127.0.0.1:8300 --policy packing_reuse
supervisorctl start cacheflow_v2_gateway
for ((i=0;i<60;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null; then break;fi
    sleep 1
done
for quota in 0 4 8 16 32; do
    /venv/main/bin/python scripts/v3_runtime.py gateway --policy packing_reuse --max-inflight 16 --max-bypasses "$quota"
    bash scripts/v3_gateway.sh 16 packing_reuse
    PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
        "v4-sg-inbatch1024-packing-reuse-q${quota}-s101" data/processed/v3/v4-dev4b3-qps4-s101.jsonl \
        --replay-url http://127.0.0.1:8100 --gateway-policy packing_reuse
done
