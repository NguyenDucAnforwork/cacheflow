#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend kernel --max-running-requests 16 --profile-transfers
supervisorctl start cacheflow_v3_sglang
for ((i=0;i<180;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null; then break;fi
    sleep 2
done
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgprofile-kernel-native-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl
/venv/main/bin/python scripts/v3_runtime.py configure --model qwen3-4b --max-inflight 16 \
    --max-num-seqs 16 --cuda-graphs --kv-capacity-tokens 43664 --upstream http://127.0.0.1:8300 --policy packing_reuse
supervisorctl start cacheflow_v2_gateway
for ((i=0;i<60;i++)); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8100/health >/dev/null; then break;fi
    sleep 1
done
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v3_sglang_bench.py \
    v4-sgprofile-kernel-packing_reuse-s101 data/processed/v3/v4-dev4b3-qps4-s101.jsonl \
    --replay-url http://127.0.0.1:8100 --gateway-policy packing_reuse
