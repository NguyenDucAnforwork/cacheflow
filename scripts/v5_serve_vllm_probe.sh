#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${CACHEFLOW_VLLM_LIVENESS_LOG:?set a fresh diagnostic output prefix}"
export PYTHONPATH="$root/scripts/v5_vllm_probe_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec bash "$root/scripts/v2_serve_vllm.sh"
