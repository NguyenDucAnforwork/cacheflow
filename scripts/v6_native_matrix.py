"""Prospective native comparison, fresh engine per regime/arrival-seed block.

--plan is read-only. Execution requires the completed main audit and idle services.
No retries: any failed arm stops the study and preserves all preceding artifacts.
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
import yaml
from v4_services import service_pid
from v5_verify import verify

CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')
BASE=Path('results/v3/sglang')
ARMS={'native':None,'fifo64':'fifo','union64':'packing_reuse','ready_fifo':'ready_fifo','packing_ready':'packing_ready'}
SOURCES=['scripts/v6_native_matrix.py','scripts/v6_sglang_bench.py','scripts/v6_native_metrics.py',
    'scripts/v5_full_histograms.py','scripts/v6_runtime.py','scripts/v6_serve_gateway.sh',
    'src/cacheflow/v6_gateway.py','src/cacheflow/v6_ready_scheduler.py','src/cacheflow/v6_replay.py',
    'scripts/v3_sglang_runtime.py','scripts/v3_serve_sglang.sh',
    'scripts/sglang_profile_hooks/sitecustomize.py','src/cacheflow/v4_sglang_delayhit.py']


def build_plan():
    blocks=[]
    for regime,qps,budget,policy,family,count in [
        ('primary',4,6,'lpm','dev4b3',60),('dfs',4,6,'dfs-weight','dev4b3',60),
        ('lowload',2,6,'lpm','dev4b3',60),('lowreuse',4,6,'lpm','lowreuse8',8),
        ('gpufit',4,10,'lpm','dev4b3',60),('abstention',4,6,'lpm','abstention12',12)]:
        for seed in [101,102,103]:
            arms=list(ARMS) if regime=='primary' else ['native','packing_ready']
            if seed==102:arms.reverse()
            elif seed==103:arms=arms[2:]+arms[:2] if len(arms)>2 else arms
            name=f'v6native1-{regime}-s{seed}'
            blocks.append(dict(regime=regime,qps=qps,budget=budget,native_policy=policy,seed=seed,
                warmup=dict(run_id=name+'-warm',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',requests=60),
                actions=[dict(run_id=name+'-'+arm,arm=arm,policy=ARMS[arm],requests=count,
                    trace=f'data/processed/v3/v5-{family}-qps{qps}-s{seed}.jsonl') for arm in arms]))
    return blocks


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();blocks=build_plan()
    scope=('Development evidence on previously exposed questions. 45 measured arms/2100 requests, 18 fresh native engines; '
        'each regime/seed block has one separate60-request native warmup, reset before every arm and fresh gateway for gateway arms. '
        'Native Direct HiCache with LPM or DFS, same-batch guard component enabled in all arms (not full Strata). '
        'All gateway arms cap64/bypass8/thread preparation/logical budget43664 or72800, uniform180s transport. '
        'Paired arms share an engine within each block; blocks have independent fresh engines. '
        'Balanced arm order, no retries. Native histograms use outside-window boundary GETs; missing coverage stays null. '
        'No GPU profiler or liveness hooks. No cross-engine absolute timing or quality-equivalence inference.')
    if a.plan:print(json.dumps(dict(scope=scope,blocks=blocks),indent=2));return
    verify()
    audit=json.loads(Path('results/v3/v6dev1_main_audit.json').read_text())
    assert audit['requests']==1440 and audit['errors']==0 and len(audit['runs'])==24
    for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']:assert service_pid(name)==0,name
    regpath=BASE/'v6native1_registration.json';assert not regpath.exists()
    for b in blocks:
        for s in [b['warmup'],*b['actions']]:
            assert not (BASE/(s['run_id']+'.setup.json')).exists()
            manifest=json.loads(Path(s['trace']).with_suffix('.manifest.json').read_text())
            assert manifest['requests']==s['requests'] and manifest['prompt_version']=='locomo-qwen-concise-v5'
    for policy in ARMS.values():
        if policy:subprocess.run([sys.executable,'-m','cacheflow.v6_replay','--policy',policy,'--help'],check=True,stdout=subprocess.DEVNULL)
    original=CONFIG.read_text();root=Path.cwd();old=f'command={root}/scripts/v2_serve_gateway.sh';assert old in original
    parentreg=json.loads(Path('results/v3/v6dev1_main_registration.json').read_text())
    assert hashlib.sha256(original.encode()).hexdigest()==parentreg['original_supervisor_sha256']
    sources={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in SOURCES}
    traces={s['trace']:hashlib.sha256(Path(s['trace']).read_bytes()).hexdigest() for b in blocks for s in [b['warmup'],*b['actions']]}
    native_pins=json.loads(subprocess.check_output(['/venv/sglang-baseline/bin/python','-c',
        "import sglang,json,hashlib,importlib.metadata as m;from pathlib import Path;r=Path(sglang.__file__).parent;names=['srt/managers/schedule_policy.py','srt/managers/cache_controller.py','srt/mem_cache/hiradix_cache.py','srt/mem_cache/memory_pool_host.py'];print(json.dumps(dict(upstream_source_sha256={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in names},package_versions={n:m.version(n) for n in ['sglang','sglang-kernel','torch','transformers','flashinfer-python','flashinfer-cubin']})))"],text=True))
    registration=dict(**native_pins,registered_utc=datetime.now(timezone.utc).isoformat(),scope=scope,blocks=blocks,
        source_sha256=sources,trace_sha256=traces,original_supervisor_sha256=hashlib.sha256(original.encode()).hexdigest(),
        main_audit_sha256=hashlib.sha256(Path('results/v3/v6dev1_main_audit.json').read_bytes()).hexdigest())
    regpath.write_text(json.dumps(registration,indent=2)+'\n');outcomes=[]
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='180',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='180',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    def call(*args):subprocess.run(list(map(str,args)),check=True,env=env)
    def wait(url):
        for _ in range(180):
            try:r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('Readiness timeout '+url)
    def stop():
        for name in ['cacheflow_v2_gateway','cacheflow_v3_sglang']:
            if service_pid(name):call('supervisorctl','stop',name)
    def runtime(*args):
        call(sys.executable,'scripts/v6_runtime.py',*args)
        path=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(path.read_text());cfg['http_read_timeout_s']=180
        path.write_text(yaml.safe_dump(cfg,sort_keys=True))
    def run(s,warmup=False):
        extra=['--warmup'] if warmup else []
        if s.get('policy'):
            runtime('gateway','--policy',s['policy'],'--max-inflight','64','--max-bypasses','8','--prepare-in-thread','--max-queue','64')
            extra+=['--replay-url','http://127.0.0.1:8100','--gateway-policy',s['policy']]
        result=subprocess.run(['/venv/sglang-baseline/bin/python','scripts/v6_sglang_bench.py',s['run_id'],s['trace'],*extra],env=env)
        row=dict(**s,warmup=warmup,returncode=result.returncode);summary=Path('results/v3/raw/sglang')/(s['run_id']+'.summary.json')
        if summary.exists():
            data=json.loads(summary.read_text());row.update(successes=data['successes'],errors=data['errors'],engine_pid=data['engine_pid'])
        outcomes.append(row);(BASE/'v6native1_outcomes.json').write_text(json.dumps(dict(scope=scope,runs=outcomes),indent=2)+'\n')
        assert result.returncode==0 and row.get('errors',1)==0 and row.get('successes')==s['requests'],row
    try:
        CONFIG.write_text(original.replace(old,f'command={root}/scripts/v6_serve_gateway.sh'))
        call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        for block in blocks:
            verify()
            for name,digest in sources.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            for name,digest in traces.items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
            assert service_pid('cacheflow_v3_sglang')==service_pid('cacheflow_v2_vllm')==0
            call(sys.executable,'scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b',
                '--gpu-kv-gib',block['budget'],'--host-kv-gib','16','--attention-backend','flashinfer','--io-backend','direct',
                '--max-running-requests','16','--schedule-policy',block['native_policy'],'--same-batch-guard')
            call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens',43664 if block['budget']==6 else 72800,'--upstream','http://127.0.0.1:8300',
                '--policy','packing_ready','--max-bypasses','8','--prepare-in-thread','--max-queue','64','--cpu-l1-bytes','16000745472')
            call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
            print('NATIVE BLOCK',json.dumps(block),flush=True)
            run(block['warmup'],True)
            for step in block['actions']:run(step)
            stop()
    finally:
        stop();CONFIG.write_text(original);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
    print('Native matrix terminal; strict audit required before claims',flush=True)


if __name__=='__main__':main()
