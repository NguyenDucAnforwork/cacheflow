#!/usr/bin/env bash
set -euo pipefail
mode=${1:?usage: set_mode.sh B0|B1|B2|B3|B4 [fifo|static_group|dhas|class_first|class_aged]}
policy=${2:-fifo}
case "$mode" in B0|B1|B2|B3|B4) ;; *) echo "invalid mode" >&2; exit 2;; esac
case "$policy" in fifo|static_group|dhas|dhas_guarded|class_first|class_aged) ;; *) echo "invalid policy" >&2; exit 2;; esac

supervisorctl stop cacheflow_gateway cacheflow_vllm cacheflow_lmcache 2>/dev/null || true
printf '%s\n' "$mode" > /workspace/.cacheflow-mode
printf '%s\n' "$policy" > /workspace/.cacheflow-policy
if [[ "$mode" == B0 || "$mode" == B1 ]]; then
    supervisorctl stop cacheflow_lmcache 2>/dev/null || true
else
    supervisorctl start cacheflow_lmcache 2>/dev/null || true
    lmcache_health_path=metrics
    [[ -e /workspace/.cacheflow-trace ]] && lmcache_health_path=docs
    for _ in $(seq 1 60); do
        if curl --silent --fail --max-time 1 "http://127.0.0.1:18080/$lmcache_health_path" >/dev/null; then break; fi
        sleep 1
    done
    curl --silent --fail --max-time 2 "http://127.0.0.1:18080/$lmcache_health_path" >/dev/null
fi

supervisorctl start cacheflow_vllm
for _ in $(seq 1 120); do
    if curl --silent --fail --max-time 1 http://127.0.0.1:8000/health >/dev/null; then break; fi
    sleep 1
done
curl --silent --fail --max-time 2 http://127.0.0.1:8000/health >/dev/null
supervisorctl start cacheflow_gateway
for _ in $(seq 1 30); do
    if curl --silent --fail --max-time 1 http://127.0.0.1:8100/health >/dev/null; then break; fi
    sleep 1
done
curl --silent --fail --max-time 2 http://127.0.0.1:8100/health
supervisorctl status cacheflow_vllm cacheflow_lmcache cacheflow_gateway || {
    [[ "$mode" == B0 || "$mode" == B1 ]] &&
        supervisorctl status cacheflow_vllm cacheflow_gateway
}
