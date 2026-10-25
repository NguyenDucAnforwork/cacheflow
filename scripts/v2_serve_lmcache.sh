#!/usr/bin/env bash
set -euo pipefail
venv=${CACHEFLOW_VENV:-/venv/main}
source "$venv/bin/activate" >/dev/null
cu13_lib="$venv/lib/python3.12/site-packages/nvidia/cu13/lib"
if [[ -d "$cu13_lib" ]]; then
    export LD_LIBRARY_PATH="$cu13_lib:${LD_LIBRARY_PATH:-}"
fi
export LMCACHE_DISABLE_BANNER=1
exec lmcache server --host 127.0.0.1 --port 5555 \
    --http-host 127.0.0.1 --http-port 18080 \
    --l1-size-gb "${CACHEFLOW_CPU_L1_GB:-16}" --eviction-policy LRU \
    --chunk-size 256 --supported-transfer-mode auto
