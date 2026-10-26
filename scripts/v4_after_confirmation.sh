#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
pid=${1:?Pass the verified live v4_confirm.py PID}
[[ "$pid" =~ ^[1-9][0-9]*$ ]]
[[ "$(tr '\0' ' ' < "/proc/$pid/cmdline")" == *v4_confirm.py* ]]
while kill -0 "$pid" 2>/dev/null;do sleep 5;done
PYTHONPATH=src /venv/main/bin/python scripts/v4_audit_confirmation.py
[[ "$(supervisorctl pid cacheflow_v2_vllm)" == 0 ]]
[[ "$(supervisorctl pid cacheflow_v3_sglang)" == 0 ]]
PYTHONPATH=src /venv/main/bin/python scripts/v4_prepare_full.py
PYTHONPATH=src /venv/main/bin/python scripts/v4_full.py
