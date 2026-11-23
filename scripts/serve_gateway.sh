#!/usr/bin/env bash
set -eo pipefail
if [[ -n ${PROC_NAME:-} ]]; then
    source /opt/supervisor-scripts/utils/logging.sh ""
fi
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home
export PYTHONPATH=/workspace/src
export CACHEFLOW_POLICY_CONFIG=/workspace/configs/policies.yaml
export CACHEFLOW_POLICY="$(cat /workspace/.cacheflow-policy 2>/dev/null || printf fifo)"
export CACHEFLOW_AGE_CAP_MS="$(cat /workspace/.cacheflow-age-cap-ms 2>/dev/null || printf 1500)"
export CACHEFLOW_TRACE=/workspace/results/raw/gateway.jsonl
exec uvicorn --factory cacheflow.gateway:create_app --host 127.0.0.1 --port 8100 --no-access-log
