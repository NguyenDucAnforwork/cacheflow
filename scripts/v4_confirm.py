"""Execute the frozen conversation-disjoint protocol; --plan has no side effects."""
import argparse
import json
import subprocess
import time
from pathlib import Path
import httpx
from v4_verify_freeze import verify
from v4_services import service_pid


def build_plan():
    actions=[]
    def add(kind,**data):actions.append(dict(kind=kind,**data))
    # One native process for all LPM pairs, then a distinct DFS baseline process.
    for policy in ['lpm','dfs-weight']:
        add('start_sg',policy=policy)
        add('sg',run_id=f'v4c1-confirm-sg-{policy}-warm-dev',trace='data/processed/v3/v4-dev4b3-qps4-s101.jsonl',arm='native')
        if policy=='lpm':
            for qps in [4,2]:
                for seed in [701,702,703]:
                    arms=['native','fifo','union'] if qps==4 else ['native','union']
                    if seed==702:arms=list(reversed(arms))
                    elif seed==703 and qps==4:arms=['fifo','native','union']
                    for arm in arms:
                        add('sg',run_id=f'v4c1-confirm-sg-lpm-qps{qps}-{arm}-s{seed}',
                            trace=f'data/processed/v3/v4c1-confirm4b-qps{qps}-s{seed}.jsonl.gz',arm=arm)
        else:
            for seed in [701,702,703]:
                add('sg',run_id=f'v4c1-confirm-sg-dfs-qps4-native-s{seed}',
                    trace=f'data/processed/v3/v4c1-confirm4b-qps4-s{seed}.jsonl.gz',arm='native')
        add('stop_sg')
    add('start_main')
    add('main',run_id='v4c1-confirm-main-warm-dev',trace='data/processed/v3/v4-dev4b3-qps4-s101.jsonl',arm='fifo64')
    for seed in [701,702,703]:
        arms=['fifo64','bundle16','union64']
        if seed==702:arms=list(reversed(arms))
        elif seed==703:arms=['bundle16','fifo64','union64']
        for arm in arms:
            add('main',run_id=f'v4c1-confirm-main-qps4-{arm}-s{seed}',
                trace=f'data/processed/v3/v4c1-confirm4b-qps4-s{seed}.jsonl.gz',arm=arm)
    add('stop_main')
    return actions


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args()
    actions=build_plan()
    if a.plan:
        for step in actions:print(json.dumps(step,sort_keys=True))
        return
    freeze,freeze_sha=verify();assert freeze['revision']==1
    def call(*args):subprocess.run(list(args),check=True)
    def stopped(name):
        assert service_pid(name)==0,name
    def wait(url):
        for _ in range(180):
            try:
                r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('readiness timeout: '+url)
    def runtime(*args):call('/venv/main/bin/python','scripts/v3_runtime.py',*args)
    for step in actions:
        verify()
        kind=step['kind'];print('FROZEN ACTION',json.dumps(step,sort_keys=True),flush=True)
        if kind=='start_sg':
            stopped('cacheflow_v2_vllm');stopped('cacheflow_v3_sglang')
            call('/venv/main/bin/python','scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b',
                '--gpu-kv-gib','6','--attention-backend','flashinfer','--io-backend','direct',
                '--max-running-requests','16','--schedule-policy',step['policy'],'--same-batch-guard')
            call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
            if step['policy']=='lpm':
                runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16',
                    '--cuda-graphs','--kv-capacity-tokens','43664','--upstream','http://127.0.0.1:8300',
                    '--policy','packing_reuse','--max-bypasses','8','--prepare-in-thread',
                    '--cpu-l1-bytes',str(freeze['host_pool_bytes']['dev_and_confirmation']))
                call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
        elif kind in {'sg','main'}:
            trace=Path(step['trace'])
            if '-warm-' not in step['run_id']:
                manifest=json.loads(trace.with_suffix('.manifest.json').read_text())
                assert manifest['method_freeze_sha256']==freeze_sha and manifest['requests']==40
            if kind=='sg':
                extra=[]
                if step['arm']!='native':
                    policy='fifo' if step['arm']=='fifo' else 'packing_reuse'
                    runtime('gateway','--policy',policy,'--max-inflight','64','--max-bypasses','8','--prepare-in-thread')
                    extra=['--replay-url','http://127.0.0.1:8100','--gateway-policy',policy]
                call('/venv/sglang-baseline/bin/python','scripts/v3_sglang_bench.py',step['run_id'],str(trace),*extra)
            else:
                policy,cap={'fifo64':('fifo',64),'bundle16':('bundle_wave',16),'union64':('packing_reuse',64)}[step['arm']]
                call('bash','scripts/v3_gateway.sh',str(cap),policy)
                call('bash','scripts/v2_reset.sh')
                call('bash','scripts/v3_run.sh',step['run_id'],str(trace))
        elif kind=='stop_sg':
            call('supervisorctl','stop','cacheflow_v3_sglang')
            # DFS has no gateway; stop only an actually running gateway.
            if service_pid('cacheflow_v2_gateway')!=0:
                call('supervisorctl','stop','cacheflow_v2_gateway')
        elif kind=='start_main':
            stopped('cacheflow_v3_sglang');stopped('cacheflow_v2_vllm')
            runtime('configure','--model','qwen3-4b','--residency-events','--max-inflight','64',
                '--max-num-seqs','16','--cuda-graphs','--kv-capacity-tokens','43664','--max-bypasses','8',
                '--prepare-in-thread','--cpu-l1-bytes',str(freeze['host_pool_bytes']['dev_and_confirmation']))
            call('bash','scripts/v2_start.sh','B2','fifo','6')
        elif kind=='stop_main':call('supervisorctl','stop','cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache')


if __name__=='__main__':main()
