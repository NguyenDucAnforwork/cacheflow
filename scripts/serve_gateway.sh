#!/usr/bin/env bash
set -euo pipefail
source /venv/main/bin/activate >/dev/null
export HF_HOME=/workspace/.hf_home
export PYTHONPATH=/workspace/src
export CACHEFLOW_POLICY_CONFIG=/workspace/configs/policies.yaml
export CACHEFLOW_TRACE=/workspace/results/raw/gateway.jsonl
exec uvicorn --factory cacheflow.gateway:create_app --host 127.0.0.1 --port 8100 --no-access-log
