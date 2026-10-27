#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${CACHEFLOW_V8_LIVENESS_LOG:?fresh diagnostic log prefix required}"
export PYTHONPATH="$root/scripts/v8_vllm_probe_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec bash "$root/scripts/v2_serve_vllm.sh"
