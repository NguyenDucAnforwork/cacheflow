#!/usr/bin/env bash
set -eo pipefail
if [[ -n ${PROC_NAME:-} ]]; then
    source /opt/supervisor-scripts/utils/logging.sh ""
fi
source /venv/main/bin/activate >/dev/null
export LD_LIBRARY_PATH="/venv/main/lib/python3.12/site-packages/nvidia/cu13/lib:${LD_LIBRARY_PATH:-}"
export LMCACHE_DISABLE_BANNER=1
args=(
    --host 127.0.0.1 --port 5555
    --http-host 127.0.0.1 --http-port 18080
    --l1-size-gb 16 --eviction-policy LRU --chunk-size 256
    --supported-transfer-mode auto
)
if [[ -e /workspace/.cacheflow-trace ]]; then
    args+=(--enable-tracing --otlp-endpoint http://127.0.0.1:4317)
fi
exec lmcache server "${args[@]}"
