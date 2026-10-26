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
import hashlib,json,subprocess,sys,urllib.request
from importlib.util import spec_from_file_location,module_from_spec
from datetime import datetime,timezone
from pathlib import Path
rid,trace=sys.argv[1:]
health=json.load(urllib.request.urlopen('http://127.0.0.1:8100/health'))
assert health['active']==health['queue']==0, 'gateway must be idle before replay'
files=sorted(p for root in ['src/cacheflow','scripts','configs'] for p in Path(root).rglob('*')
             if p.is_file() and p.suffix in ['.py','.sh','.yaml','.json'])
source_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
runtime=json.loads(Path('.cacheflow-v3-runtime.json').read_text())
spec=spec_from_file_location('v3_model','scripts/v3_model.py');module=module_from_spec(spec);spec.loader.exec_module(module)
model=module.get_model(runtime.get('model_key','qwen3-1.7b'))
gpu_bytes=int(Path('.cacheflow-v2-gpu-kv-bytes').read_text())
capacity=(gpu_bytes//(16*model['bytes_per_token'])-1)*16
assert runtime['kv_capacity_tokens']==capacity, ('reservation capacity mismatch', runtime['kv_capacity_tokens'], capacity)
pid=int(subprocess.check_output(['supervisorctl','pid','cacheflow_v2_vllm'],text=True))
actual_argv=[x.decode() for x in Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0') if x]
def actual_value(flag):
    positions=[i for i,x in enumerate(actual_argv) if x==flag]
    assert positions, ('missing engine option',flag)
    return actual_argv[positions[-1]+1]
assert int(actual_value('--kv-cache-memory-bytes'))==gpu_bytes, 'engine/marker KV budget mismatch'
assert model['path'] in actual_argv, 'engine/model mismatch'
assert int(actual_value('--max-num-seqs'))==runtime['max_num_seqs']
assert int(actual_value('--max-num-batched-tokens'))==runtime['max_num_batched_tokens']
assert ('--enforce-eager' in actual_argv)==runtime['enforce_eager']
public_env={}
for item in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
    key,_,value=item.partition(b'=')
    if key in [b'PYTHONHASHSEED',b'VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES',b'VLLM_BATCH_INVARIANT']:
        public_env[key.decode()]=value.decode()
assert bool(runtime.get('batch_invariant',False))==(public_env.get('VLLM_BATCH_INVARIANT','0')=='1')
c=dict(run_id=rid,trace_path=trace,runtime=runtime, model=model,
       actual_engine_env=public_env,
       actual_engine_argv_list=actual_argv,
       gateway_config=Path('.cacheflow-v3-gateway.yaml').read_text(),
       gpu_kv_bytes=int(Path('.cacheflow-v2-gpu-kv-bytes').read_text()),
       actual_engine_argv=Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0',b' ').decode(),
       source_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
       source_diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff','HEAD'])).hexdigest(),
       source_files_sha256=source_files, gateway_before=health,
       captured_utc=datetime.now(timezone.utc).isoformat())
Path(f'results/v3/{rid}.setup.json').write_text(json.dumps(c,indent=2)+'\n')
PY
CACHEFLOW_RESULTS_DIR="$root/results/v3" CACHEFLOW_GATEWAY_LOG="$root/results/v3/raw/gateway.jsonl" \
    CACHEFLOW_CAPTURE_TEXT=1 bash scripts/v2_run.sh "$id" "$trace" "$url"
/venv/main/bin/python - "$id" <<'PY'
import json,os,sys,urllib.request
from pathlib import Path
health=json.load(urllib.request.urlopen('http://127.0.0.1:8100/health'))
path=Path(f'results/v3/{sys.argv[1]}.setup.json')
c=json.loads(path.read_text());c['gateway_after']=health
path.write_text(json.dumps(c,indent=2)+'\n')
summary=json.loads(Path(f'results/v3/raw/{sys.argv[1]}.summary.json').read_text())
if summary['errors']:
    Path(f'results/v3/{sys.argv[1]}.invalid').write_text(f"{summary['errors']} failed request(s); diagnostic only.\n")
    assert os.environ.get('CACHEFLOW_ALLOW_FAILED_DIAGNOSTIC')=='1', 'request failure invalidates performance run'
else:
    sys.path.insert(0,'scripts')
    from v3_analyze_runs import load
    try:
        load(sys.argv[1])
    except Exception as exc:
        Path(f'results/v3/{sys.argv[1]}.invalid').write_text('Integrity audit failed: '+repr(exc)+'\n')
        raise
if c['runtime'].get('residency_events'):
    state=health['residency']
    assert state['subscriber_running'] and state['known'] and state['gaps']==0 and state['hash_contract_verified'], state
PY
