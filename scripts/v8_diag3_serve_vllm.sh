#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${CACHEFLOW_V8_ENGINE_LOG:?fresh engine stderr/stdout log required}"
[[ ! -e "$CACHEFLOW_V8_ENGINE_LOG" ]] || { echo 'engine log exists; no automatic restart' >&2; exit 2; }
if [[ -n "${CACHEFLOW_V8_LIVENESS_LOG:-}" ]]; then
    export PYTHONPATH="$root/scripts/v8_vllm_probe_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
fi
exec > >(tee "$CACHEFLOW_V8_ENGINE_LOG") 2>&1
exec bash "$root/scripts/v2_serve_vllm.sh"
