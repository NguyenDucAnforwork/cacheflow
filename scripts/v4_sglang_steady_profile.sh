#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
backend=${1:-direct}
run_id=${2:-sglang_gpu_steady}
[[ "$backend" == direct || "$backend" == kernel ]]
[[ "$(supervisorctl pid cacheflow_v2_vllm)" == 0 ]]
[[ "$(supervisorctl pid cacheflow_v3_sglang)" == 0 ]]
/venv/main/bin/python scripts/v3_sglang_runtime.py configure --model qwen3-4b --gpu-kv-gib 6 \
    --attention-backend flashinfer --io-backend "$backend" --host-kv-gib 16 --max-running-requests 16 \
    --schedule-policy lpm --same-batch-guard --profile-transfers
supervisorctl start cacheflow_v3_sglang
ready=0
for ((i=0;i<180;i++));do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8300/health >/dev/null;then ready=1;break;fi
    sleep 2
done
[[ "$ready" == 1 ]]
PYTHONPATH=src /venv/sglang-baseline/bin/python scripts/v4_sglang_steady_profile.py --io-backend "$backend" --run-id "$run_id"
supervisorctl stop cacheflow_v3_sglang
