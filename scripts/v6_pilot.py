"""Prospective readiness pilot: old union, FIFO, gate-only and gated union.

Development data already exposed under V5. Not a new holdout/full benchmark.
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

CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')
ROOT=Path.cwd()


def build_plan():
    actions=[]
    for dataset,seed in [('dev',101),('stress',702)]:
        arms=['fifo64','union64','ready_fifo','packing_ready']
        if dataset=='stress':arms.reverse()
        trace=f'data/processed/v3/v5-dev4b3-qps4-s{seed}.jsonl' if dataset=='dev' else f'data/processed/v3/v5-confirm4b-qps4-s{seed}.jsonl.gz'
        for arm in arms:actions.append(dict(dataset=dataset,seed=seed,arm=arm,trace=trace,run_id=f'v6pilot2-{dataset}-{arm}-s{seed}'))
    return actions


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();steps=build_plan()
    if a.plan:print(json.dumps(dict(scope='Development pilot only',timeout_s=180,actions=steps),indent=2));return
    verify()
    for policy in ['ready_fifo','packing_ready']:
        subprocess.run([sys.executable,'-m','cacheflow.v6_replay','--policy',policy,'--help'],check=True,stdout=subprocess.DEVNULL)
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0
    registration_path=Path('results/v3/v6pilot2_registration.json');assert not registration_path.exists()
    assert all(not Path(f"results/v3/{s['run_id']}.setup.json").exists() for s in steps)
    sources=['scripts/v6_pilot.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh','src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','src/cacheflow/v6_replay.py','scripts/v6_run.sh','scripts/v6_v2_run.sh']
    assert Path('src/cacheflow/v6_replay.py').read_text()==Path('src/cacheflow/v2_replay.py').read_text().replace('"sglang_dfs-weight"]','"sglang_dfs-weight", "ready_fifo", "packing_ready"]')
    assert Path('scripts/v6_v2_run.sh').read_text()==Path('scripts/v2_run.sh').read_text().replace('python -m cacheflow.v2_replay','python -m cacheflow.v6_replay')
    assert Path('scripts/v6_run.sh').read_text()==Path('scripts/v3_run.sh').read_text().replace('bash scripts/v2_run.sh','bash scripts/v6_v2_run.sh')
    original=CONFIG.read_text();assert f'command={ROOT}/scripts/v2_serve_gateway.sh' in original
    assert Path('scripts/v6_serve_gateway.sh').read_text()==Path('scripts/v2_serve_gateway.sh').read_text().replace('cacheflow.gateway:create_app','cacheflow.v6_gateway:create_app')
    registration=dict(registered_utc=datetime.now(timezone.utc).isoformat(),actions=steps,
        source_sha256={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
        parent_v5_seal_sha256=hashlib.sha256(Path('results/v3/v5_prompt_freeze.json').read_bytes()).hexdigest(),
        original_supervisor_sha256=hashlib.sha256(original.encode()).hexdigest(),
        method='Same logical union budget/cap64/bypass8, add at most one admitted request without first nonempty text per >=1024-token exact prefix. Gate-only FIFO ablation has the same gate and bypass bound but no union budget. First text is a frontend signal, not a physical pin guarantee.',
        scope='Prospective development pilot on already exposed60dev/40stressQA, no fresh holdout or full contribution claim. Fixed four-arm order reversed on stress. Fresh engine per dataset block; uniform60dev warmup; fresh gateway and cache reset per arm. Stop block on any failed/incomplete arm; no retries. Allclient/pool/upstream timeouts180s; primary3600s data are not pooled. Native probes/profilers off. Configured host flags match historical V5; effective lazy heap measured separately.')
    registration_path.write_text(json.dumps(registration,indent=2)+'\n');results=[]
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
        call(sys.executable,'scripts/v6_runtime.py',*args)
        path=Path('.cacheflow-v3-gateway.yaml');c=yaml.safe_load(path.read_text());c['http_read_timeout_s']=180;path.write_text(yaml.safe_dump(c,sort_keys=True))
    def record(step):
        rid=step['run_id'];gateway=psutil.Process(service_pid('cacheflow_v2_gateway'));engine=psutil.Process(service_pid('cacheflow_v2_vllm'))
        assert 'cacheflow.v6_gateway:create_app' in gateway.cmdline()
        assert not engine.environ().get('CACHEFLOW_VLLM_LIVENESS_LOG')
        before=dict(gateway_pid=gateway.pid,gateway_argv=gateway.cmdline(),source_sha256=registration['source_sha256'],
            upstream_profile=False,native_probe=False)
        Path(f'results/v3/{rid}.v6_entrypoint.json').write_text(json.dumps(before,indent=2)+'\n')
        proc=subprocess.run(['bash','scripts/v6_run.sh',rid,step['trace']],env=env)
        path=Path(f'results/v3/raw/{rid}.summary.json');out=dict(**step,returncode=proc.returncode,summary_present=path.exists())
        if path.exists():
            s=json.loads(path.read_text());out.update(requests=s['requests'],successes=s['successes'],errors=s['errors'])
        if proc.returncode or out.get('errors',1):
            Path(f'results/v3/{rid}.invalid').write_text('V6 pilot failed/incomplete; inspect retained return code and raw artifacts. No successful-only performance claim.\n')
        results.append(out);Path('results/v3/v6pilot2_outcomes.json').write_text(json.dumps(dict(scope=registration['scope'],runs=results),indent=2)+'\n')
        return proc.returncode==0 and out.get('errors',1)==0
    try:
        CONFIG.write_text(original.replace(f'command={ROOT}/scripts/v2_serve_gateway.sh',f'command={ROOT}/scripts/v6_serve_gateway.sh'))
        call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        for dataset in ['dev','stress']:
            verify()
            runtime('configure','--model','qwen3-4b','--residency-events','--max-inflight','64','--max-num-seqs','16',
                '--cuda-graphs','--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','64',
                '--cpu-l1-bytes','16000745472')
            call('bash','scripts/v2_start.sh','B2','fifo','6')
            status=httpx.get('http://127.0.0.1:18080/status',timeout=5).json()
            Path(f'results/v3/v6pilot2-{dataset}_host_status.json').write_text(json.dumps(status,indent=2)+'\n')
            warm=dict(dataset=dataset,seed=101,arm='fifo64',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',run_id=f'v6pilot2-{dataset}-warm')
            phase_steps=[warm,*[s for s in steps if s['dataset']==dataset]]
            for step in phase_steps:
                for name,digest in registration['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
                policy={'fifo64':'fifo','union64':'packing_reuse','ready_fifo':'ready_fifo','packing_ready':'packing_ready'}[step['arm']]
                h=httpx.get('http://127.0.0.1:8100/health',timeout=5).json();assert h['active']==h['queue']==0
                runtime('gateway','--policy',policy,'--max-inflight','64')
                call('supervisorctl','restart','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health');call('bash','scripts/v2_reset.sh')
                print('V6 PILOT',json.dumps(step),flush=True)
                if not record(step):break
            stop()
    finally:
        stop();CONFIG.write_text(original);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
    print('Readiness pilot terminal; inspect errors and complete per-arm evidence before any claim',flush=True)


if __name__=='__main__':main()
