#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
: "${CACHEFLOW_V9_WATERMARK_MODE:?explicit native mode required}"
: "${CACHEFLOW_V9_WATERMARK_PROOF:?fresh native proof prefix required}"
: "${CACHEFLOW_V9_EXPECTED_CONNECTOR_SHA:?registered native source SHA required}"
: "${CACHEFLOW_V9_ENGINE_LOG:?fresh native engine log required}"
[[ "$CACHEFLOW_V9_WATERMARK_MODE" == reference || "$CACHEFLOW_V9_WATERMARK_MODE" == idempotent ]] || exit 2
[[ ! -e "$CACHEFLOW_V9_ENGINE_LOG" ]] || { echo 'engine log exists; no automatic restart'; exit 2; }
export PYTHONPATH="$root/scripts/v9_native_hooks:$root/src${PYTHONPATH:+:$PYTHONPATH}"
exec > >(tee "$CACHEFLOW_V9_ENGINE_LOG") 2>&1
exec bash "$root/scripts/v2_serve_vllm.sh"
