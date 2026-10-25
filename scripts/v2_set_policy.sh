#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
policy=${1:?usage: v2_set_policy.sh fifo|dhas}
case "$policy" in
    fifo) mode=B2 ;;
    dhas) mode=B3 ;;
    *) echo "invalid policy: $policy" >&2; exit 2 ;;
esac
current_mode=$(cat "$root/.cacheflow-mode" 2>/dev/null || printf unknown)
case "$current_mode" in B2|B3) ;; *) echo "CPU-tier engine is not selected" >&2; exit 2 ;; esac
health=$(curl --silent --show-error --fail --max-time 5 http://127.0.0.1:8100/health)
python3 - "$health" <<'PY_CHECK'
import json, sys
state=json.loads(sys.argv[1])
if state.get('active') != 0 or state.get('queue') != 0:
    raise SystemExit('refusing policy switch while gateway has active/queued requests')
PY_CHECK
engine_before=$(supervisorctl pid cacheflow_v2_vllm)
lmcache_before=$(supervisorctl pid cacheflow_v2_lmcache)
[[ "$engine_before" =~ ^[1-9][0-9]*$ && "$lmcache_before" =~ ^[1-9][0-9]*$ ]] || {
    echo "serving process PID unavailable" >&2; exit 1;
}
supervisorctl stop cacheflow_v2_gateway >/dev/null
printf '%s\n' "$mode" > "$root/.cacheflow-mode"
printf '%s\n' "$policy" > "$root/.cacheflow-policy"
supervisorctl start cacheflow_v2_gateway >/dev/null
ready=0
for ((i=0; i<30; i++)); do
    if health=$(curl --silent --fail --max-time 2 http://127.0.0.1:8100/health); then
        if python3 - "$health" "$policy" <<'PY_CHECK'
import json, sys
raise SystemExit(0 if json.loads(sys.argv[1]).get('policy') == sys.argv[2] else 1)
PY_CHECK
        then ready=1; break; fi
    fi
    sleep 1
done
[[ "$ready" == 1 ]] || { echo "gateway policy did not become ready" >&2; exit 1; }
[[ $(supervisorctl pid cacheflow_v2_vllm) == "$engine_before" ]] || {
    echo "vLLM PID changed during policy switch" >&2; exit 1;
}
[[ $(supervisorctl pid cacheflow_v2_lmcache) == "$lmcache_before" ]] || {
    echo "LMCache PID changed during policy switch" >&2; exit 1;
}
printf 'V2 policy %s; vLLM PID %s; LMCache PID %s\n' \
    "$policy" "$engine_before" "$lmcache_before"
