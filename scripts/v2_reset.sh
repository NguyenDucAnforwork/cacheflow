#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=$(cat "$root/.cacheflow-mode" 2>/dev/null || printf unknown)
case "$mode" in B1|B2|B3) ;; *) echo "unknown V2 mode: $mode" >&2; exit 2 ;; esac
health=$(curl --silent --show-error --fail --max-time 5 http://127.0.0.1:8100/health)
python3 - "$health" <<'PY_CHECK'
import json, sys
state=json.loads(sys.argv[1])
if state.get('active') != 0 or state.get('queue') != 0:
    raise SystemExit('refusing cache reset while gateway has active/queued requests')
PY_CHECK
curl --silent --show-error --fail --max-time 5 http://127.0.0.1:8000/health >/dev/null
sleep 2  # allow asynchronous KV stores to finish after the last response
if [[ "$mode" != B1 ]]; then
    curl --silent --show-error --fail --max-time 15 -X POST \
        http://127.0.0.1:18080/cache/clear >/dev/null
fi
curl --silent --show-error --fail --max-time 15 -X POST \
    http://127.0.0.1:8000/reset_prefix_cache >/dev/null
sleep 1
if [[ "$mode" != B1 ]]; then
    curl --silent --show-error --fail --max-time 5 \
        http://127.0.0.1:18080/metrics | python3 -c '
import sys
values=[]
for line in sys.stdin:
    if line.startswith("lmcache_mp_l1_memory_usage_bytes"):
        values.append(float(line.rsplit(" ", 1)[1]))
if not values or sum(values) != 0:
    raise SystemExit("LMCache L1 gauge missing or nonzero after clear")
'
fi
printf 'V2 caches cleared for mode %s\n' "$mode"
