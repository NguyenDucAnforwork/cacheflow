"""Execute the sealed full study, audit/archive each run, never retry failures."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import httpx
import psutil
import yaml
from v4_services import service_pid
from v6_full_plan import build_plan
from v6_freeze_full import verify_full,PATH,sha
from v6_native_metrics import capture,summarize
from v6_raw_archive import archive
from v6_full_continuation_r1 import verify_continuation, remaining_steps, retained_outcome

CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')
ROOT=Path.cwd();SERVICES=['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args()
    if a.plan:print(json.dumps(dict(actions=build_plan()[1:],retained_run_id=build_plan()[0]['run_id'],status='read-only;29unexecuted arms; requires original seal and explicit R1 continuation registration'),indent=2));return
    parent,seal,freeze=verify_full();verify_continuation()
    for name in SERVICES:assert service_pid(name)==0,name
    regpath=Path('results/v3/v6full1_continuation_r1_execution.json');assert not regpath.exists()
    for step in remaining_steps():
        base=Path('results/v3/sglang' if step['engine']=='sg' else 'results/v3')
        assert not (base/(step['run_id']+'.setup.json')).exists(),step['run_id']
    original=CONFIG.read_text();old=f'command={ROOT}/scripts/v2_serve_gateway.sh';assert old in original
    regpath.write_text(json.dumps(dict(freeze_sha256=sha(PATH),original_supervisor_sha256=sha(CONFIG),actions=remaining_steps(),continuation_registration_sha256=sha('results/v3/v6full1_continuation_r1_registration.json')),indent=2)+'\n')
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='3600',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='3600',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    outcomes=[retained_outcome()];phase='preflight';step=None
    def call(*args):subprocess.run(list(map(str,args)),check=True,env=env)
    def stop():
        errors=[]
        for name in SERVICES:
            try:
                if service_pid(name):call('supervisorctl','stop',name)
            except Exception as exc:errors.append(dict(service=name,error=repr(exc)))
        if errors:raise RuntimeError('Failed to stop serving services: '+json.dumps(errors))
    def wait(url):
        for _ in range(180):
            try:r=httpx.get(url,timeout=2);r.raise_for_status();return
            except httpx.HTTPError:time.sleep(2)
        raise RuntimeError('Readiness timeout '+url)
    def runtime(*args):
        call(sys.executable,'scripts/v6_runtime.py',*args)
        path=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(path.read_text());cfg['http_read_timeout_s']=3600
        path.write_text(yaml.safe_dump(cfg,sort_keys=True))
    def gateway(policy,cap):
        runtime('gateway','--policy',policy,'--max-inflight',cap,'--max-queue','512','--max-bypasses','8','--prepare-in-thread')
    def main_run(step,warm=False):
        rid=step['run_id'];gateway(step['policy'],step['cap']);call('supervisorctl','restart','cacheflow_v2_gateway')
        wait('http://127.0.0.1:8100/health');call('bash','scripts/v2_reset.sh')
        gp=psutil.Process(service_pid('cacheflow_v2_gateway'));ep=psutil.Process(service_pid('cacheflow_v2_vllm'))
        assert 'cacheflow.v6_gateway:create_app' in gp.cmdline() and not ep.environ().get('CACHEFLOW_VLLM_LIVENESS_LOG')
        Path(f'results/v3/{rid}.v6_entrypoint.json').write_text(json.dumps(dict(gateway_pid=gp.pid,gateway_argv=gp.cmdline(),source_sha256=freeze['actor_sha256'],native_probe=False,upstream_profile=False,warmup=warm),indent=2)+'\n')
        before=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        call('bash','scripts/v6_run.sh',rid,step['trace'])
        after=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        raw=Path('results/v3/raw');summary=json.loads((raw/(rid+'.summary.json')).read_text())
        data=(raw/(rid+'.jsonl')).read_bytes();rows=[json.loads(l) for l in data.splitlines()]
        snapshot=summarize(rid,before,after,rows,summary,'vllm');snapshot['request_file_sha256']=sha(raw/(rid+'.jsonl'))
        Path(f'results/v3/{rid}.itl_histogram.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    def sg_run(step,warm=False):
        extra=['--warmup'] if warm else []
        if step['policy']:
            gateway(step['policy'],step['cap']);extra+=['--replay-url','http://127.0.0.1:8100','--gateway-policy',step['policy']]
        call('/venv/sglang-baseline/bin/python','scripts/v6_sglang_bench.py',step['run_id'],step['trace'],*extra)
    try:
        CONFIG.write_text(original.replace(old,f'command={ROOT}/scripts/v6_serve_gateway.sh'))
        call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        for step in remaining_steps():
            phase='preflight';verify_full();verify_continuation();assert all(service_pid(n)==0 for n in SERVICES)
            assert shutil.disk_usage(ROOT).free>=96*1024**2,'Insufficient free disk for a complete raw run; preserve prior evidence and stop'
            rid=step['run_id'];sg=step['engine']=='sg';budget=step['budget'];print('FULL ARM',json.dumps(step),flush=True)
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens',43664 if budget==6 else 72800,'--max-bypasses','8','--prepare-in-thread','--max-queue','512',
                '--cpu-l1-bytes',freeze['host_payload_bytes'],'--upstream','http://127.0.0.1:8300' if sg else 'http://127.0.0.1:8000')
            if sg:
                call(sys.executable,'scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b','--gpu-kv-gib',budget,'--host-kv-gib','48',
                    '--attention-backend','flashinfer','--io-backend','direct','--max-running-requests','16','--schedule-policy',step['native_policy'],'--same-batch-guard')
                call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
                call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
            else:
                call('bash','scripts/v2_start.sh','B2','fifo',budget)
                Path(f'results/v3/{rid}.host_status.json').write_text(json.dumps(httpx.get('http://127.0.0.1:18080/status',timeout=5).json(),indent=2)+'\n')
            warm=dict(step,run_id=rid+'-warm',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',requests=60,policy=None if sg else 'fifo',cap=64)
            runner=sg_run if sg else main_run
            phase='warmup';runner(warm,True)
            phase='measured';runner(step);stop()
            phase='audit';call(sys.executable,'scripts/v6_audit_full_run_r1.py',rid)
            auditpath=Path('results/v3')/(rid+'.full_audit_r1.json');archivepath=Path('results/v3')/(rid+'.archive_r1.json')
            phase='archive';archive(auditpath,archivepath)
            outcomes.append(dict(run_id=rid,complete=True,audit_sha256=sha(auditpath),archive_sha256=sha(archivepath)))
            Path('results/v3/v6full1_continuation_r1_outcomes.json').write_text(json.dumps(dict(runs=outcomes),indent=2)+'\n')
    except Exception as exc:
        if step is not None and phase in {'warmup','measured','audit'}:
            failedbase=Path('results/v3/sglang' if step['engine']=='sg' else 'results/v3')
            (failedbase/(step['run_id']+'.invalid')).write_text('Full study stopped during '+phase+': '+repr(exc)+'; no performance claim before correction/audit.\n')
        Path('results/v3/v6full1_continuation_r1_interruption.json').write_text(json.dumps(dict(error=repr(exc),phase=phase,last_step=step,completed_arms=len(outcomes),scope='Study stopped; retain failed/unexecuted arms. No retries or successful-only complete-stage table.'),indent=2)+'\n')
        raise
    finally:
        try:stop()
        finally:
            CONFIG.write_text(original);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
    call(sys.executable,'scripts/v6_audit_full_r1.py')


if __name__=='__main__':main()
