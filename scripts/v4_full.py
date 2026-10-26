"""Frozen full1986-QA study; --plan prints the actual execution plan without mutations."""
import argparse
import json
import subprocess
import time
from pathlib import Path
import httpx
from v4_verify_freeze import verify
from v4_services import service_pid


def build_plan():
    actions=[];current=None;index=0
    def add(kind,**data):actions.append(dict(kind=kind,**data))
    def engine(policy,budget,seed):
        nonlocal current,index
        if current==(policy,budget):return
        if current is not None:add('stop_sg')
        index+=1;add('start_sg',policy=policy,budget=budget)
        add('sg',run_id=f'v4c1-full-warm-sg{index}-{policy}-g{budget}-s{seed}',
            trace='data/processed/v3/v4-dev4b3-qps4-s101.jsonl',arm='native')
        current=(policy,budget)
    for seed in [901,902,903]:
        arms=['native','fifo','union','dfs']
        if seed==902:arms=list(reversed(arms))
        elif seed==903:arms=['fifo','native','dfs','union']
        trace='data/processed/v3/v4-full4b-qps4-s901.jsonl.gz' if seed==901 else f'data/processed/v3/v4c1-full4b-qps4-s{seed}.jsonl.gz'
        for arm in arms:
            engine('dfs-weight' if arm=='dfs' else 'lpm',6,seed)
            add('sg',run_id=f'v4c1-full-sg-g6-qps4-{arm}-s{seed}',trace=trace,arm='native' if arm=='dfs' else arm)
    engine('lpm',10,901)
    for arm in ['native','union']:
        add('sg',run_id=f'v4c1-full-sg-g10-qps4-{arm}-s901',trace='data/processed/v3/v4-full4b-qps4-s901.jsonl.gz',arm=arm)
    add('stop_sg');add('start_main')
    add('main',run_id='v4c1-full-main-warm-dev',trace='data/processed/v3/v4-dev4b3-qps4-s101.jsonl',arm='fifo64')
    for arm in ['fifo64','bundle16','union64']:
        add('main',run_id=f'v4c1-full-main-g6-qps4-{arm}-s901',trace='data/processed/v3/v4-full4b-qps4-s901.jsonl.gz',arm=arm)
    add('stop_main');return actions


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();actions=build_plan()
    if a.plan:
        for step in actions:print(json.dumps(step,sort_keys=True))
        return
    freeze,digest=verify();assert freeze['revision']==1
    def call(*args):subprocess.run(list(args),check=True)
    def runtime(*args):call('/venv/main/bin/python','scripts/v3_runtime.py',*args)
    def wait(url):
        for _ in range(180):
            try:r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('readiness timeout: '+url)
    for step in actions:
        verify();print('FULL ACTION',json.dumps(step,sort_keys=True),flush=True);kind=step['kind']
        if kind=='start_sg':
            assert service_pid('cacheflow_v2_vllm')==service_pid('cacheflow_v3_sglang')==0
            call('/venv/main/bin/python','scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b',
                '--gpu-kv-gib',str(step['budget']),'--host-kv-gib','48','--attention-backend','flashinfer',
                '--io-backend','direct','--max-running-requests','16','--schedule-policy',step['policy'],'--same-batch-guard')
            call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
            if step['policy']=='lpm':
                capacity=43664 if step['budget']==6 else 72800
                runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16',
                    '--cuda-graphs','--kv-capacity-tokens',str(capacity),'--upstream','http://127.0.0.1:8300',
                    '--policy','packing_reuse','--max-bypasses','8','--prepare-in-thread','--max-queue','512',
                    '--cpu-l1-bytes',str(freeze['host_pool_bytes']['full']))
                call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
        elif kind in {'sg','main'}:
            trace=Path(step['trace'])
            if '-warm-' not in step['run_id']:
                m=json.loads(trace.with_suffix('.manifest.json').read_text())
                assert m['requests']==1986 and m['model_revision']==freeze['model_revision']
                assert m['prompt_version']==freeze['prompt_version']
                assert m['trace_sha256']==freeze['parent_full_trace_sha256'] or m.get('method_freeze_sha256')==digest
            if kind=='sg':
                extra=[]
                if step['arm']!='native':
                    policy='fifo' if step['arm']=='fifo' else 'packing_reuse'
                    runtime('gateway','--policy',policy,'--max-inflight','64','--max-bypasses','8','--prepare-in-thread','--max-queue','512')
                    extra=['--replay-url','http://127.0.0.1:8100','--gateway-policy',policy]
                call('/venv/sglang-baseline/bin/python','scripts/v3_sglang_bench.py',step['run_id'],str(trace),*extra)
            else:
                policy,cap={'fifo64':('fifo',64),'bundle16':('bundle_wave',16),'union64':('packing_reuse',64)}[step['arm']]
                call('bash','scripts/v3_gateway.sh',str(cap),policy);call('bash','scripts/v2_reset.sh')
                call('bash','scripts/v3_run.sh',step['run_id'],str(trace))
        elif kind=='stop_sg':
            call('supervisorctl','stop','cacheflow_v3_sglang')
            if service_pid('cacheflow_v2_gateway'):call('supervisorctl','stop','cacheflow_v2_gateway')
        elif kind=='start_main':
            assert service_pid('cacheflow_v3_sglang')==service_pid('cacheflow_v2_vllm')==0
            # These arms do not consume a residency observer; no event-publisher
            # overhead is needed in this supplemental full-stack comparison.
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','512',
                '--cpu-l1-bytes',str(freeze['host_pool_bytes']['full']))
            call('bash','scripts/v2_start.sh','B2','fifo','6')
        elif kind=='stop_main':call('supervisorctl','stop','cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache')
    call('/venv/main/bin/python','scripts/v4_audit_full.py')
    # Separate kernel-I/O diagnostic after every unprofiled measurement.
    call('bash','scripts/v4_sglang_steady_profile.sh','kernel','v4_kernel_gpu_steady')


if __name__=='__main__':main()
