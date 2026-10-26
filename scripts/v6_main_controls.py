"""Matched main-stack controls; fresh engine per arm and no retries."""
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
from v6_native_metrics import capture,summarize

ROOT=Path.cwd();CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')
ARMS={'fifo64':('fifo',64),'packing_ready':('packing_ready',64)}


def build_plan():
    steps=[]
    for regime,qps,budget,family,count in [('lowload',2,6,'dev4b3',60),('lowreuse',4,6,'lowreuse8',8),
            ('gpufit',4,10,'dev4b3',60),('abstention',4,6,'abstention12',12)]:
        for seed in [101,102,103]:
            arms=list(ARMS)
            if seed==102:arms.reverse()
            for arm in arms:steps.append(dict(regime=regime,qps=qps,budget=budget,requests=count,
                arm=arm,seed=seed,policy=ARMS[arm][0],cap=ARMS[arm][1],
                trace=f'data/processed/v3/v5-{family}-qps{qps}-s{seed}.jsonl',run_id=f'v6controls1-main-{regime}-{arm}-s{seed}'))
    return steps


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();steps=build_plan()
    if a.plan:print(json.dumps(dict(scope='Prospective development matrix; not fresh semantic confirmation',actions=steps),indent=2));return
    verify()
    native=json.loads(Path('results/v3/sglang/v6native1_audit.json').read_text())
    assert native['complete'] and native['requests']==2100 and native['errors']==0 and len(native['runs'])==45
    for policy in ['ready_fifo','packing_ready']:
        subprocess.run([sys.executable,'-m','cacheflow.v6_replay','--policy',policy,'--help'],check=True,stdout=subprocess.DEVNULL)
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0
    registration_path=Path('results/v3/v6controls1_main_registration.json');assert not registration_path.exists()
    assert all(not Path(f"results/v3/{s['run_id']}.setup.json").exists() for s in steps)
    sources=['scripts/v6_main_controls.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh','src/cacheflow/v6_gateway.py',
        'src/cacheflow/v6_ready_scheduler.py','src/cacheflow/v6_replay.py','scripts/v6_run.sh','scripts/v6_v2_run.sh','scripts/v6_native_metrics.py','scripts/v5_full_histograms.py']
    for step in steps:
        m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
        assert m['requests']==step['requests'] and m['prompt_version']=='locomo-qwen-concise-v5'
    original=CONFIG.read_text();assert f'command={ROOT}/scripts/v2_serve_gateway.sh' in original
    registration=dict(registered_utc=datetime.now(timezone.utc).isoformat(),actions=steps,
        native_audit_sha256=hashlib.sha256(Path('results/v3/sglang/v6native1_audit.json').read_bytes()).hexdigest(),
        trace_sha256={s['trace']:hashlib.sha256(Path(s['trace']).read_bytes()).hexdigest() for s in steps},
        source_sha256={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in sources},
        parent_v5_seal_sha256=hashlib.sha256(Path('results/v3/v5_prompt_freeze.json').read_bytes()).hexdigest(),
        original_supervisor_sha256=hashlib.sha256(original.encode()).hexdigest(),
        scope='Main-stack matched controls on exposed QA, FIFO64 vs readiness+union64 across lowload/lowreuse/developmentGPUfit/abstention and3arrival schedules.24measured arms840requests and1440separate warmups. Fresh main/LMCache per arm, reset/fresh gateway, same180s read/pool/upstream timeout/keepalive0/preparation. GPU6or10GiB and host flag16000745472bytes. Nativehistogram boundary GETs, no GPUprofiler or livenessprobe. Retain all failures and proceed to next independent preplanned fresh engine, no retries. Not a full benchmark, semantic holdout or production liveness proof.')
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
        assert 'cacheflow.v6_gateway:create_app' in gateway.cmdline() and not engine.environ().get('CACHEFLOW_VLLM_LIVENESS_LOG')
        Path(f'results/v3/{rid}.v6_entrypoint.json').write_text(json.dumps(dict(gateway_pid=gateway.pid,gateway_argv=gateway.cmdline(),
            source_sha256=registration['source_sha256'],native_probe=False,upstream_profile=False),indent=2)+'\n')
        before=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        run=subprocess.run(['bash','scripts/v6_run.sh',rid,step['trace']],env=env)
        after=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        path=Path(f'results/v3/raw/{rid}.summary.json');row=dict(step,returncode=run.returncode,summary_present=path.exists())
        if path.exists():
            s=json.loads(path.read_text());row.update(requests=s['requests'],successes=s['successes'],errors=s['errors'])
            data=Path(f'results/v3/raw/{rid}.jsonl').read_bytes();requests=[json.loads(l) for l in data.splitlines()]
            snapshot=summarize(rid,before,after,requests,s,'vllm');snapshot['request_file_sha256']=hashlib.sha256(data).hexdigest()
            Path(f'results/v3/{rid}.itl_histogram.json').write_text(json.dumps(snapshot,indent=2)+'\n')
        if run.returncode or row.get('errors',1):Path(f'results/v3/{rid}.invalid').write_text('Failed/incomplete independent matrix arm; retained, no retries or successful-only latency claims.\n')
        results.append(row);Path('results/v3/v6controls1_main_outcomes.json').write_text(json.dumps(dict(scope=registration['scope'],runs=results),indent=2)+'\n')
        return run.returncode==0 and row.get('errors',1)==0
    try:
        CONFIG.write_text(original.replace(f'command={ROOT}/scripts/v2_serve_gateway.sh',f'command={ROOT}/scripts/v6_serve_gateway.sh'))
        call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        for step in steps:
            verify()
            assert hashlib.sha256(Path(step['trace']).read_bytes()).hexdigest()==registration['trace_sha256'][step['trace']]
            for name,digest in registration['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            runtime('configure','--model','qwen3-4b','--residency-events','--max-inflight','64','--max-num-seqs','16',
                '--cuda-graphs','--kv-capacity-tokens',str(43664 if step['budget']==6 else 72800),'--max-bypasses','8','--prepare-in-thread','--max-queue','64',
                '--cpu-l1-bytes','16000745472')
            call('bash','scripts/v2_start.sh','B2','fifo',str(step['budget']))
            Path(f"results/v3/{step['run_id']}.host_status.json").write_text(json.dumps(httpx.get('http://127.0.0.1:18080/status',timeout=5).json(),indent=2)+'\n')
            warm=dict(arm='fifo64',policy='fifo',cap=64,seed=101,trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',run_id=step['run_id']+'-warm')
            for current in [warm,step]:
                runtime('gateway','--policy',current['policy'],'--max-inflight',str(current['cap']))
                call('supervisorctl','restart','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health');call('bash','scripts/v2_reset.sh')
                print('V6 MAIN MATRIX',json.dumps(current),flush=True)
                if not record(current):break
            stop()
    finally:
        stop();CONFIG.write_text(original);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
    print('Main controls terminal; strict audit and final full study remain required',flush=True)


if __name__=='__main__':main()
