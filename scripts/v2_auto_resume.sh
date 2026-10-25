#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
install_pid=${1:?usage: v2_auto_resume.sh UV_INSTALL_PID}
venv=${CACHEFLOW_VENV:-/venv/main}
cd "$root"
log() { printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
log "waiting for pinned package install PID $install_pid (maximum 6 hours)"
for ((i=0; i<720; i++)); do
    if ! kill -0 "$install_pid" 2>/dev/null; then break; fi
    sleep 30
done
if kill -0 "$install_pid" 2>/dev/null; then
    log "package install did not finish within 6 hours"
    exit 1
fi
log "package install process exited; checking pinned versions"
"$venv/bin/python" - <<'PY_CHECK'
from importlib.metadata import PackageNotFoundError, version
for name, expected in {'vllm': '0.22.0', 'lmcache': '0.5.3',
                       'transformers': '5.6.2', 'torch': '2.11.0+cu128'}.items():
    try:
        actual = version(name)
    except PackageNotFoundError:
        actual = None
    if actual != expected:
        raise SystemExit(f'{name}: expected {expected}, found {actual}')
print('pinned package versions pass')
PY_CHECK
log "installing local project and lightweight test dependencies"
uv pip install --python "$venv/bin/python" -e "$root" pytest psutil
"$venv/bin/python" scripts/v2_preflight.py
PYTHONPATH=src "$venv/bin/python" -m pytest -q
log "checking traces with installed tokenizer"
PYTHONPATH=src "$venv/bin/python" - <<'PY_CHECK'
import json
from pathlib import Path
from transformers import AutoTokenizer
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace
snapshot = '/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e'
tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
for name in ('e1_2k_50ms_1pair', 'locomo_b1_fullctx_1qa',
             'locomo_dev_2conv_interleaved', 'locomo_dev_2conv_session'):
    path = Path('data/processed/v2') / f'{name}.jsonl'
    rows = load_trace(path)
    manifest = json.loads(path.with_suffix('.manifest.json').read_text())
    assert trace_digest(rows) == manifest['trace_sha256'], name
    for row in rows:
        assert len(tokenizer.encode(row.prompt, add_special_tokens=False)) == row.input_tokens, row.request_id
    print(name, len(rows), manifest['trace_sha256'])
PY_CHECK
log "checking exclusive access to V2 services and ports"
for service in vllm lmcache gateway; do
    if [[ -e "/etc/supervisor/conf.d/cacheflow_v2_$service.conf" ]]; then
        log "V2 supervisor config already exists; manual review required"
        exit 1
    fi
done
python3 - <<'PY_CHECK'
import socket
for port in (8000, 8100, 18080):
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(('127.0.0.1', port)) == 0:
            raise SystemExit(f'port {port} already in use')
PY_CHECK
bash scripts/v2_install_services.sh
cleanup() { bash scripts/v2_stop.sh || true; }
trap cleanup EXIT
log "starting B1, 32K context, 8 GiB GPU KV"
bash scripts/v2_start.sh B1 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-b1-fullctx-1qa-auto-r1 data/processed/v2/locomo_b1_fullctx_1qa.jsonl
python3 - <<'PY_CHECK'
import json
from pathlib import Path
root = Path('results/v2')
run = json.loads((root / 'raw/v2-b1-fullctx-1qa-auto-r1.summary.json').read_text())
metrics = json.loads((root / 'v2-b1-fullctx-1qa-auto-r1.metrics_summary.json').read_text())
if run['requests'] != 1 or run['successes'] != 1 or run['errors'] != 0:
    raise SystemExit(f'B1 pilot did not return one successful request: {run}')
print('B1 TTFT ms', run['arrival_ttft_p50_ms'], 'VRAM peak MiB', metrics['vram_peak_mib'])
PY_CHECK
log "B1 full-context pilot passed; inspect results/v2/raw and metrics summary"
