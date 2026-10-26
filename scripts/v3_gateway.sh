#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cap=${1:?usage: v3_gateway.sh MAX_INFLIGHT}
policy=${2:-fifo}
state=$(curl -fsS http://127.0.0.1:8100/health)
python3 - "$state" <<'PY'
import json,sys
s=json.loads(sys.argv[1]);assert s['active']==0 and s['queue']==0,'gateway not idle'
PY
/venv/main/bin/python "$root/scripts/v3_runtime.py" gateway --max-inflight "$cap" --policy "$policy"
supervisorctl restart cacheflow_v2_gateway
for ((i=0;i<60;i++)); do
    if curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1; then exit 0; fi
    sleep 1
done
echo 'gateway readiness timeout' >&2
exit 1
