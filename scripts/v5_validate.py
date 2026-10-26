"""Fixed-method V5 prompt-repair validation, with actual --plan execution graph."""
import argparse
import json
import subprocess
import time
import os
import yaml
from pathlib import Path
import httpx
from v4_services import service_pid
from v5_verify import verify


def build_plan():
    actions=[]
    def add(kind,**values):actions.append(dict(kind=kind,**values))
    for policy,budget in [('lpm',6),('dfs-weight',6),('lpm',10)]:
        add('start_sg',policy=policy,budget=budget)
        add('sg',run_id=f'v5r2-dev-warm-{policy}-g{budget}',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',arm='native')
        if budget==10:
            regimes=[('gpufit',4)]
        elif policy=='dfs-weight':regimes=[('dfs',4)]
        else:regimes=[('lpm',4),('lpm',2),('lowreuse',4),('abstention',4)]
        for regime,qps in regimes:
            for seed in [101,102,103]:
                arms=['native','fifo','union'] if regime=='lpm' and qps==4 else ['native','union']
                if seed==102:arms=list(reversed(arms))
                elif seed==103 and len(arms)==3:arms=['fifo','native','union']
                family={'lowreuse':'lowreuse8','abstention':'abstention12'}.get(regime,'dev4b3')
                trace=f'data/processed/v3/v5-{family}-qps{qps}-s{seed}.jsonl'
                for arm in arms:add('sg',run_id=f'v5r2-dev-{regime}-g{budget}-qps{qps}-{arm}-s{seed}',trace=trace,arm=arm)
        add('stop_sg')
    add('start_main')
    add('main',run_id='v5r2-dev-main-warm-dev',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',arm='fifo64')
    base=['fifo16','fifo64','lpm16','bundle16','dhas16','union64']
    for seed in [101,102,103]:
        arms=base if seed==101 else list(reversed(base)) if seed==102 else base[2:]+base[:2]
        for arm in arms:add('main',run_id=f'v5r2-dev-main-qps4-{arm}-s{seed}',
            trace=f'data/processed/v3/v5-dev4b3-qps4-s{seed}.jsonl',arm=arm)
    add('stop_main');return actions


def execute(actions):
    parent,seal=verify()
    env=dict(os.environ,CACHEFLOW_REQUEST_READ_TIMEOUT_S='3600',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='3600',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    def call(*args):subprocess.run(list(args),check=True,env=env)
    def runtime(*args):
        call('/venv/main/bin/python','scripts/v3_runtime.py',*args)
        cfg_path=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(cfg_path.read_text())
        cfg['http_read_timeout_s']=3600;cfg_path.write_text(yaml.safe_dump(cfg,sort_keys=True))
    def wait(url):
        for _ in range(180):
            try:r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('readiness timeout '+url)
    budget=6
    for step in actions:
        verify();kind=step['kind'];print('V5 ACTION',json.dumps(step,sort_keys=True),flush=True)
        if kind=='start_sg':
            budget=step['budget']
            assert service_pid('cacheflow_v2_vllm')==service_pid('cacheflow_v3_sglang')==0
            call('/venv/main/bin/python','scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b',
                '--gpu-kv-gib',str(budget),'--host-kv-gib','16','--attention-backend','flashinfer','--io-backend','direct',
                '--max-running-requests','16','--schedule-policy',step['policy'],'--same-batch-guard')
            call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens',str(43664 if budget==6 else 72800),'--upstream','http://127.0.0.1:8300',
                '--policy','packing_reuse','--max-bypasses','8','--prepare-in-thread','--max-queue','64',
                '--cpu-l1-bytes',str(parent['host_pool_bytes']['dev_and_confirmation']))
            call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
        elif kind in {'sg','main'}:
            m=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
            assert m['prompt_version']=='locomo-qwen-concise-v5' and m['abstention_style']=='official_consistent_system_and_user'
            if kind=='sg':
                extra=[]
                if step['arm']!='native':
                    policy='fifo' if step['arm']=='fifo' else 'packing_reuse'
                    runtime('gateway','--policy',policy,'--max-inflight','64','--max-bypasses','8','--prepare-in-thread','--max-queue','64')
                    extra=['--replay-url','http://127.0.0.1:8100','--gateway-policy',policy]
                call('/venv/sglang-baseline/bin/python','scripts/v3_sglang_bench.py',step['run_id'],step['trace'],*extra)
            else:
                policy,cap={'fifo16':('fifo',16),'fifo64':('fifo',64),'lpm16':('lpm_real',16),
                    'bundle16':('bundle_wave',16),'dhas16':('dhas',16),'union64':('packing_reuse',64)}[step['arm']]
                state=httpx.get('http://127.0.0.1:8100/health',timeout=10).json();assert state['active']==state['queue']==0
                runtime('gateway','--policy',policy,'--max-inflight',str(cap))
                call('supervisorctl','restart','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
                call('bash','scripts/v2_reset.sh')
                call('bash','scripts/v3_run.sh',step['run_id'],step['trace'])
        elif kind=='stop_sg':
            call('supervisorctl','stop','cacheflow_v2_gateway','cacheflow_v3_sglang')
        elif kind=='start_main':
            assert service_pid('cacheflow_v3_sglang')==service_pid('cacheflow_v2_vllm')==0
            runtime('configure','--model','qwen3-4b','--residency-events','--max-inflight','64','--max-num-seqs','16',
                '--cuda-graphs','--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','64',
                '--cpu-l1-bytes',str(parent['host_pool_bytes']['dev_and_confirmation']))
            call('bash','scripts/v2_start.sh','B2','fifo','6')
        elif kind=='stop_main':call('supervisorctl','stop','cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache')


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args();plan=build_plan()
    if a.plan:
        for step in plan:print(json.dumps(step,sort_keys=True))
    else:execute(plan)


if __name__=='__main__':main()
