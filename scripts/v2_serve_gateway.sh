#!/usr/bin/env bash
set -euo pipefail
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
venv=${CACHEFLOW_VENV:-/venv/main}
source "$venv/bin/activate" >/dev/null
export HF_HOME=${HF_HOME:-/workspace/.hf_home}
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
export CACHEFLOW_POLICY_CONFIG="$root/configs/policies.yaml"
export CACHEFLOW_POLICY="$(cat "$root/.cacheflow-policy" 2>/dev/null || printf fifo)"
export CACHEFLOW_TRACE="$root/results/v2/raw/gateway.jsonl"
mkdir -p "$root/results/v2/raw"
exec uvicorn --factory cacheflow.gateway:create_app --host 127.0.0.1 --port 8100 --no-access-log
