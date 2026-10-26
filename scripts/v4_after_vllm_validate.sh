#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
pid=${1:?Pass the verified live v4_vllm_replicate PID}
[[ "$pid" =~ ^[1-9][0-9]*$ ]]
[[ "$(tr '\0' ' ' < "/proc/$pid/cmdline")" == *v4_vllm_replicate.sh* ]]
while kill -0 "$pid" 2>/dev/null;do sleep 5;done
# A missing PID alone is not success: require all expected artifacts and idle GPU
# services before proceeding. Failure aborts this coordinator without a restart.
PYTHONPATH=src /venv/main/bin/python scripts/v4_audit_vllm_dev.py
[[ "$(supervisorctl pid cacheflow_v2_vllm)" == 0 ]]
[[ "$(supervisorctl pid cacheflow_v3_sglang)" == 0 ]]
bash scripts/v4_sglang_validate.sh
