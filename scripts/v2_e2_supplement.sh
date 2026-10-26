#!/usr/bin/env bash
# Separately labelled chat-template validation and P-SESSION exploratory pairs.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
kind=${1:?usage: v2_e2_supplement.sh chat|session}
case "$kind" in
    chat) trace=data/processed/v2/e2_validation_chat_s71.jsonl; namespace=v2-e2-chat-val2-s71 ;;
    session) trace=data/processed/v2/locomo_dev_2conv_session.jsonl; namespace=v2-e3-session-dev2-qps2 ;;
    *) exit 2 ;;
esac
[[ -f "$trace" ]] || { echo "missing $trace"; exit 2; }
trap 'bash scripts/v2_stop.sh' EXIT
for mode in B1 B2; do
    id="$namespace-${mode,,}-4g"
    echo "$(date -u +%FT%TZ) START $id"
    bash scripts/v2_start.sh "$mode" fifo 4
    curl --silent --show-error --fail --max-time 60 http://127.0.0.1:8000/v1/completions \
        -H 'Content-Type: application/json' \
        -d '{"model":"cacheflow-qwen3-1.7b","prompt":"A brief warmup. Answer: 1","max_tokens":1,"temperature":0}' >/dev/null
    bash scripts/v2_reset.sh
    curl --silent --fail http://127.0.0.1:8100/health > "results/v2/raw/$id.reset_health.json"
    CACHEFLOW_CAPTURE_TEXT=1 bash scripts/v2_run.sh "$id" "$trace"
    echo "$(date -u +%FT%TZ) DONE $id"
done
