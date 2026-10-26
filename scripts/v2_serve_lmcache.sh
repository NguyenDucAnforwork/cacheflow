#!/usr/bin/env bash
set -euo pipefail
venv=${CACHEFLOW_VENV:-/venv/main}
source "$venv/bin/activate" >/dev/null
cu13_lib="$venv/lib/python3.12/site-packages/nvidia/cu13/lib"
if [[ -d "$cu13_lib" ]]; then
    export LD_LIBRARY_PATH="$cu13_lib:${LD_LIBRARY_PATH:-}"
fi
export LMCACHE_DISABLE_BANNER=1
root=${CACHEFLOW_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
command=(lmcache)
chunk_size=256
cpu_l1_gib=${CACHEFLOW_CPU_L1_GB:-16}
if [[ -s "$root/.cacheflow-v3-runtime.json" ]]; then
    chunk_size=$(python -c 'import json,sys; print(json.load(open(sys.argv[1]))["chunk_size"])' "$root/.cacheflow-v3-runtime.json")
    cpu_l1_gib=$(PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python -c 'import json,sys; from cacheflow.v4_resources import lmcache_gib_flag; c=json.load(open(sys.argv[1])); print(lmcache_gib_flag(c["cpu_l1_bytes"]) if c.get("cpu_l1_bytes") is not None else c.get("cpu_l1_gib",16))' "$root/.cacheflow-v3-runtime.json")
    if python -c 'import json,sys; sys.exit(not json.load(open(sys.argv[1])).get("kv_events"))' "$root/.cacheflow-v3-runtime.json"; then
        export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
        export CACHEFLOW_KV_EVENTS="$root/results/v3/raw/kv_events.jsonl"
        command=(python -m cacheflow.v3_lmcache_profile)
    fi
fi
exec "${command[@]}" server --host 127.0.0.1 --port 5555 \
    --http-host 127.0.0.1 --http-port 18080 \
    --l1-size-gb "$cpu_l1_gib" --eviction-policy LRU \
    --chunk-size "$chunk_size" --supported-transfer-mode auto
