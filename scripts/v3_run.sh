#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$root"
id=${1:?usage: v3_run.sh RUN_ID TRACE [URL]}
trace=${2:?missing trace}
url=${3:-http://127.0.0.1:8100}
[[ -s .cacheflow-v3-runtime.json ]] || { echo 'configure V3 runtime first'; exit 2; }
[[ ! -e "results/v3/$id.setup.json" ]] || { echo 'setup already exists'; exit 2; }
/venv/main/bin/python - "$id" "$trace" <<'PY'
import hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
rid,trace=sys.argv[1:]
pid=int(subprocess.check_output(['supervisorctl','pid','cacheflow_v2_vllm'],text=True))
c=dict(run_id=rid,trace_path=trace,runtime=json.loads(Path('.cacheflow-v3-runtime.json').read_text()),
       gateway_config=Path('.cacheflow-v3-gateway.yaml').read_text(),
       gpu_kv_bytes=int(Path('.cacheflow-v2-gpu-kv-bytes').read_text()),
       actual_engine_argv=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode(),
       source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
       source_diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff','HEAD'])).hexdigest(),
       captured_utc=datetime.now(timezone.utc).isoformat())
Path(f'results/v3/{rid}.setup.json').write_text(json.dumps(c,indent=2)+'\n')
PY
CACHEFLOW_RESULTS_DIR="$root/results/v3" CACHEFLOW_GATEWAY_LOG="$root/results/v3/raw/gateway.jsonl" \
    CACHEFLOW_CAPTURE_TEXT=1 bash scripts/v2_run.sh "$id" "$trace" "$url"
