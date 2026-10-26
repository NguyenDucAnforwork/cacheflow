"""Prospective off/on/off liveness diagnostic after the live V5 run terminates.

Uniform180s diagnostic timeout, exact failed history, no retries or latency claim.
Each phase has a fresh engine, dev warmup, three seed701 arms then seed702 union.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
import httpx
import psutil
import yaml
from v4_services import service_pid
from v5_verify import verify

ROOT=Path.cwd()
CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_vllm.conf')
NAMESPACE='v5diag-stall1'


def build_plan():
    steps=[]
    for phase in ['offA','on','offB']:
        for label,arm,trace in [
            ('warm','fifo64','data/processed/v3/v5-dev4b3-qps4-s101.jsonl'),
            ('history-fifo','fifo64','data/processed/v3/v5-confirm4b-qps4-s701.jsonl.gz'),
            ('history-bundle','bundle16','data/processed/v3/v5-confirm4b-qps4-s701.jsonl.gz'),
            ('history-union','union64','data/processed/v3/v5-confirm4b-qps4-s701.jsonl.gz'),
            ('target','union64','data/processed/v3/v5-confirm4b-qps4-s702.jsonl.gz')]:
            steps.append(dict(phase=phase,probe=phase=='on',label=label,arm=arm,trace=trace,run_id=f'{NAMESPACE}-{phase}-{label}'))
    return steps


def alive(process):
    try:return process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:return False


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--after-pid',type=int);a=p.parse_args()
    steps=build_plan()
    if a.plan:
        print(json.dumps(dict(scope='Diagnostic only; not V5 study continuation',timeout_s=180,actions=steps),indent=2));return
    assert a.after_pid, 'Supply verified live V5 pipeline PID'
    process=psutil.Process(a.after_pid);assert alive(process) and 'scripts/v5_pipeline.py' in process.cmdline()
    born=process.create_time();verify()
    output=Path(f'results/v3/{NAMESPACE}_registration.json');assert not output.exists()
    for step in steps:assert not Path(f"results/v3/{step['run_id']}.setup.json").exists()
    original=CONFIG.read_text();original_sha=hashlib.sha256(original.encode()).hexdigest()
    assert f'command={ROOT}/scripts/v2_serve_vllm.sh' in original
    source_paths=['scripts/v5_stall_diagnostic.py','scripts/v5_serve_vllm_probe.sh',
        'scripts/v5_vllm_probe_hooks/sitecustomize.py','src/cacheflow/v5_liveness_probe.py']
    registration=dict(registered_utc=datetime.now(timezone.utc).isoformat(),wait_pipeline_pid=process.pid,
        wait_pipeline_birth=born,diagnostic_timeout_s=180,actions=steps,
        source_sha256={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_paths},
        supervisor_original_sha256=original_sha,
        scope='Fresh-process off/on/off, exact warm/history/target trace order, same frozen policy/model/budgets/output cap.180s diagnostic timeouts uniformly differ from3600s primary. No retries, no source patch to upstream, all outcomes diagnostic. Stop phase if an earlier warm/history arm fails. Restore supervisor command and stop serving after all phases.')
    output.write_text(json.dumps(registration,indent=2)+'\n')
    print('Registered diagnostic waiting on live pipeline',a.after_pid,flush=True)
    while alive(process):
        assert process.create_time()==born;time.sleep(5)
    failed='v5r2-confirm-main-qps4-union64-s702'
    summary_path=Path(f'results/v3/raw/{failed}.summary.json')
    assert summary_path.exists() and Path(f'results/v3/{failed}.invalid').exists(), 'Missing retained terminal diagnostic outcome; do not reset blindly'
    old=json.loads(summary_path.read_text());assert old['requests']==40
    assert not Path('results/v3/v5r2_full_audit.json').exists()
    for name,digest in registration['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest
    assert hashlib.sha256(CONFIG.read_bytes()).hexdigest()==original_sha, 'Supervisor config changed while waiting'
    assert service_pid('cacheflow_v3_sglang')==0
    results=[]
    env=dict(os.environ,CACHEFLOW_REQUEST_READ_TIMEOUT_S='180',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='180',
        CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0',CACHEFLOW_ALLOW_FAILED_DIAGNOSTIC='1')
    def call(*args):subprocess.run(list(map(str,args)),check=True,env=env)
    def stop():
        for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache']:
            if service_pid(name):call('supervisorctl','stop',name)
    def wait(url):
        for _ in range(180):
            try:r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('Readiness failed: '+url)
    def runtime(*args):
        call(sys.executable,'scripts/v3_runtime.py',*args)
        path=Path('.cacheflow-v3-gateway.yaml');c=yaml.safe_load(path.read_text());c['http_read_timeout_s']=180
        path.write_text(yaml.safe_dump(c,sort_keys=True))
    def switch(probe):
        assert service_pid('cacheflow_v2_vllm')==0
        content=original
        if probe:
            content=content.replace(f'command={ROOT}/scripts/v2_serve_vllm.sh',f'command={ROOT}/scripts/v5_serve_vllm_probe.sh')
            content=content.replace('environment=',f'environment=CACHEFLOW_VLLM_LIVENESS_LOG="{ROOT}/results/v3/raw/{NAMESPACE}-probe",',1)
        CONFIG.write_text(content);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_vllm')
    try:
        stop()
        for phase in ['offA','on','offB']:
            verify();switch(phase=='on')
            runtime('configure','--model','qwen3-4b','--residency-events','--max-inflight','64','--max-num-seqs','16',
                '--cuda-graphs','--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','64',
                '--cpu-l1-bytes','16000745472')
            call('bash','scripts/v2_start.sh','B2','fifo','6')
            for step in [s for s in steps if s['phase']==phase]:
                rid=step['run_id'];policy,cap={'fifo64':('fifo',64),'bundle16':('bundle_wave',16),'union64':('packing_reuse',64)}[step['arm']]
                h=httpx.get('http://127.0.0.1:8100/health',timeout=5).json();assert h['active']==h['queue']==0
                runtime('gateway','--policy',policy,'--max-inflight',str(cap))
                call('supervisorctl','restart','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health');call('bash','scripts/v2_reset.sh')
                print('DIAGNOSTIC',json.dumps(step),flush=True)
                run=subprocess.run(['bash','scripts/v3_run.sh',rid,step['trace']],env=env)
                path=Path(f'results/v3/raw/{rid}.summary.json')
                result=dict(**step,returncode=run.returncode,summary_present=path.exists())
                if path.exists():
                    s=json.loads(path.read_text());result.update(requests=s['requests'],successes=s['successes'],errors=s['errors'],duration_s=s['duration_s'])
                Path(f'results/v3/{rid}.invalid').write_text('Separate liveness diagnostic, uniform180s timeout; probe perturbation differs by phase. Never include in primary performance/quality comparisons.\n')
                results.append(result)
                Path(f'results/v3/{NAMESPACE}_outcomes.json').write_text(json.dumps(dict(scope=registration['scope'],runs=results),indent=2)+'\n')
                if run.returncode or result.get('errors',1):break
            stop()
    finally:
        stop();switch(False)
    print('Liveness diagnostic terminal; root-cause review and method/full study remain required',flush=True)


if __name__=='__main__':main()
