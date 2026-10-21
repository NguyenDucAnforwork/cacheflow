#!/usr/bin/env bash
set -euo pipefail

# Call only with no in-flight requests; LMCache's force-clear can invalidate active IO.
health=$(curl --silent --show-error --fail --max-time 3 http://127.0.0.1:8100/health)
[[ "$health" == *'"queue":0'* && "$health" == *'"active":0'* ]] || {
    echo "Gateway is not idle; refusing cache reset: $health" >&2
    exit 1
}
curl --silent --show-error --fail --max-time 10 -X POST \
    -H 'content-type: application/json' -d '{"tier":"l1","force":true}' \
    http://127.0.0.1:18080/cache/clear >/dev/null
curl --silent --show-error --fail --max-time 10 -X POST \
    http://127.0.0.1:8000/reset_prefix_cache >/dev/null
sleep 1
cache_bytes=$(curl --silent --show-error --fail --max-time 3 http://127.0.0.1:18080/metrics |
    awk '$1=="lmcache_mp_l1_memory_usage_bytes" {print $2; exit}')
[[ "$cache_bytes" == 0 || "$cache_bytes" == 0.0 ]] || {
    echo "LMCache L1 is not empty after reset: $cache_bytes" >&2
    exit 1
}
echo "GPU prefix cache and LMCache L1 cleared; gateway idle"
