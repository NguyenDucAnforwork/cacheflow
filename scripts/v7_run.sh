#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
id=${1:?usage: v7_run.sh RUN_ID TRACE IMPLEMENTATION [URL]}
trace=${2:?missing trace}
implementation=${3:?explicit reference/epoch implementation required}
url=${4:-http://127.0.0.1:8100}
case "$id" in
    *[!A-Za-z0-9._-]*|'') echo 'Invalid run ID' >&2; exit 2 ;;
esac
export PYTHONPATH="$root/src:$root/scripts${PYTHONPATH:+:$PYTHONPATH}"
before="results/v3/$id.v7_identity_before.json"
after="results/v3/$id.v7_identity_after.json"
pair="results/v3/$id.v7_identity_pair.json"
[[ ! -e "$before" && ! -e "$after" && ! -e "$pair" && ! -e "results/v3/$id.setup.json" ]] || { echo 'run ID already exists' >&2; exit 2; }
fail() {
    if [[ ! -e "results/v3/$id.invalid" ]]; then
        printf 'V7 replay/identity boundary failed; retained, no retry or successful-only latency claim.\n' > "results/v3/$id.invalid"
    fi
}
trap fail ERR
policy=$(cat .cacheflow-policy)
/venv/main/bin/python scripts/v7_gateway_identity.py capture "$url" "$policy" "$implementation" --fresh --output "$before"
# Retain the existing request/metric/output capture and strict source accounting.
bash scripts/v6_run.sh "$id" "$trace" "$url"
/venv/main/bin/python scripts/v7_gateway_identity.py capture "$url" "$policy" "$implementation" --output "$after"
/venv/main/bin/python scripts/v7_gateway_identity.py verify-pair "$before" "$after" --requests "results/v3/raw/$id.jsonl" --output "$pair"
trap - ERR
