#!/usr/bin/env bash
set -euo pipefail
mode=${1:?usage: set_policy.sh B2|B3|B4 fifo|dhas|dhas_guarded|static_group}
policy=${2:?missing policy}
case "$mode:$policy" in
    B2:fifo|B3:dhas|B3:dhas_guarded|B4:static_group) ;;
    *) echo "unsupported mode/policy pair" >&2; exit 2 ;;
esac
current_mode=$(cat /workspace/.cacheflow-mode)
case "$current_mode" in B2|B3|B4) ;; *) echo "running engine is not the two-tier stack" >&2; exit 1;; esac
supervisorctl status cacheflow_vllm cacheflow_lmcache >/dev/null
health=$(curl --silent --show-error --fail --max-time 3 http://127.0.0.1:8100/health)
[[ "$health" == *'"queue":0'* && "$health" == *'"active":0'* ]] || {
    echo "Gateway is not idle; refusing policy switch: $health" >&2
    exit 1
}
supervisorctl stop cacheflow_gateway >/dev/null
printf '%s\n' "$mode" > /workspace/.cacheflow-mode
printf '%s\n' "$policy" > /workspace/.cacheflow-policy
supervisorctl start cacheflow_gateway >/dev/null
for _ in $(seq 1 30); do
    if curl --silent --fail --max-time 1 http://127.0.0.1:8100/health | grep -q "\"policy\":\"$policy\""; then
        echo "Gateway policy $policy; engine and LMCache processes preserved"
        exit 0
    fi
    sleep 1
done
echo "gateway policy health check failed" >&2
exit 1
