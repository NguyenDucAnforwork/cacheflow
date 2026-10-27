"""Execute the sealed18-arm V10 screen, audit/archive, stop on first failure."""
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
from v6_native_metrics import capture,summarize
from v6_raw_archive import archive,sha
from v10_epoch_study import BASE,PREFIX,FREEZE,read,write,verify
from v10_epoch_plan import build_plan

from v10_epoch_native import engine_config,capture_identity,validate_identity

ROOT=Path.cwd();VLLM_CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_vllm.conf');CONFIG=Path('/etc/supervisor/conf.d/cacheflow_v2_gateway.conf')
MARKER=Path('.cacheflow-v7-implementation');SERVICES=['cacheflow_v2_gateway','cacheflow_v2_vllm','cacheflow_v2_lmcache','cacheflow_v3_sglang']


def execute():
    parent,seal,f=verify()
    assert all(service_pid(n)==0 for n in SERVICES),'Serving must be idle'
    execution=BASE/(PREFIX+'_execution.json');assert not execution.exists() and not MARKER.exists()
    for step in f['actions']:
        meta=BASE/'sglang' if step['engine']=='sg' else BASE
        assert not list(meta.glob(step['run_id']+'*')),step['run_id']
    original=CONFIG.read_text();original_vllm=VLLM_CONFIG.read_text();old=f'command={ROOT}/scripts/v2_serve_gateway.sh';assert old in original
    write(execution,dict(freeze_sha256=sha(FREEZE),original_supervisor_sha256=sha(CONFIG),original_vllm_supervisor_sha256=sha(VLLM_CONFIG),actions=f['actions']))
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='180',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='180',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    outcomes=[];phase='preflight';step=None
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
        path=Path('.cacheflow-v3-gateway.yaml');c=yaml.safe_load(path.read_text());c['http_read_timeout_s']=180;path.write_text(yaml.safe_dump(c,sort_keys=True))
    def gateway(policy,cap,implementation):
        MARKER.write_text(implementation+'\n')
        runtime('gateway','--policy',policy,'--max-inflight',cap,'--max-queue','512','--max-bypasses','8','--prepare-in-thread')
    def main_run(current,warm=False):
        rid=current['run_id'];gateway(current['policy'],current['cap'],current['implementation'])
        call('supervisorctl','restart','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health');call('bash','scripts/v2_reset.sh')
        gp=psutil.Process(service_pid('cacheflow_v2_gateway'));ep=psutil.Process(service_pid('cacheflow_v2_vllm'))
        assert 'cacheflow.v7_gateway:create_app' in gp.cmdline() and not ep.environ().get('CACHEFLOW_VLLM_LIVENESS_LOG')
        write(BASE/(rid+'.v7_entrypoint.json'),dict(gateway_pid=gp.pid,gateway_argv=gp.cmdline(),source_sha256=f['actor_sha256'],native_probe=False,upstream_profile=False,warmup=warm))
        before=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        native_before=capture_identity(current,f)
        call('bash','scripts/v7_run.sh',rid,current['trace'],current['implementation'])
        native_after=capture_identity(current,f)
        proof=dict(before=native_before,after=native_after,freeze_sha256=sha(FREEZE))
        request_rows=[json.loads(line) for line in (BASE/'raw'/(rid+'.jsonl')).read_text().splitlines()]
        validate_identity(current,proof,request_rows,f)
        write(BASE/(rid+'.v10_native_identity.json'),proof)
        after=capture('http://127.0.0.1:8000/metrics','vllm','cacheflow_v2_vllm')
        raw=BASE/'raw';rows=[json.loads(l) for l in (raw/(rid+'.jsonl')).read_text().splitlines()];s=read(raw/(rid+'.summary.json'))
        snapshot=summarize(rid,before,after,rows,s,'vllm');snapshot['request_file_sha256']=sha(raw/(rid+'.jsonl'))
        write(BASE/(rid+'.itl_histogram.json'),snapshot)
    def sg_run(current,warm=False):
        args=['--warmup'] if warm else []
        if current['policy']:
            gateway(current['policy'],current['cap'],current['implementation'])
            args+=['--replay-url','http://127.0.0.1:8100','--gateway-policy',current['policy'],'--scheduler-implementation',current['implementation']]
        call('/venv/sglang-baseline/bin/python','scripts/v7_sglang_bench.py',current['run_id'],current['trace'],*args)
    try:
        CONFIG.write_text(original.replace(old,f'command={ROOT}/scripts/v7_serve_gateway.sh'))
        call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        for step in f['actions']:
            phase='preflight';verify(True);assert all(service_pid(n)==0 for n in SERVICES)
            assert shutil.disk_usage(ROOT).free>=96*1024**2,'Insufficient disk; preserve evidence and stop'
            rid=step['run_id'];sg=step['engine']=='sg';print('V10 DEVELOPMENT',json.dumps(step),flush=True)
            VLLM_CONFIG.write_text(original_vllm if sg else engine_config(original_vllm,step,f))
            call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_vllm')
            MARKER.write_text('reference\n')
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','512',
                '--cpu-l1-bytes',f['host_payload_bytes'],'--upstream','http://127.0.0.1:8300' if sg else 'http://127.0.0.1:8000')
            if sg:
                call(sys.executable,'scripts/v3_sglang_runtime.py','configure','--model','qwen3-4b','--gpu-kv-gib','6','--host-kv-gib','16',
                    '--attention-backend','flashinfer','--io-backend','direct','--max-running-requests','16','--schedule-policy',step['native_policy'],'--same-batch-guard')
                call('supervisorctl','start','cacheflow_v3_sglang');wait('http://127.0.0.1:8300/health')
                call('supervisorctl','start','cacheflow_v2_gateway');wait('http://127.0.0.1:8100/health')
            else:
                call('bash','scripts/v2_start.sh','B2','fifo','6')
                write(BASE/(rid+'-host-status.json'),httpx.get('http://127.0.0.1:18080/status',timeout=5).json())
            warm=dict(step,run_id=rid+'-warm',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',policy=None if sg else 'fifo',implementation=None if sg else 'reference',cap=64)
            runner=sg_run if sg else main_run
            phase='warmup';runner(warm,True)
            phase='measured';runner(step);stop()
            phase='audit';call(sys.executable,'scripts/v10_audit_epoch_run.py',rid)
            ap=BASE/(rid+'.v10_audit.json');zp=BASE/(rid+'.v10_archive.json');phase='archive';archive(ap,zp)
            outcomes.append(dict(run_id=rid,complete=True,audit_sha256=sha(ap),archive_sha256=sha(zp)))
            (BASE/(PREFIX+'_outcomes.json')).write_text(json.dumps(dict(runs=outcomes),indent=2)+'\n')
    except Exception as exc:
        if step is not None and phase in {'warmup','measured','audit'}:
            meta=BASE/'sglang' if step['engine']=='sg' else BASE;p=meta/(step['run_id']+'.invalid')
            if not p.exists():p.write_text('V10 study failed during '+phase+': '+repr(exc)+'; no retries or successful-only performance claim.\n')
        write(BASE/(PREFIX+'_interruption.json'),dict(complete=False,error=repr(exc),phase=phase,last_step=step,completed_arms=len(outcomes)))
        raise
    finally:
        cleanup=[]
        try:stop()
        except Exception as exc:cleanup.append(dict(operation='stop',error=repr(exc)))
        try:CONFIG.write_text(original);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway')
        except Exception as exc:cleanup.append(dict(operation='restore_supervisor',error=repr(exc)))
        try:VLLM_CONFIG.write_text(original_vllm);call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_vllm')
        except Exception as exc:cleanup.append(dict(operation='restore_vllm_supervisor',error=repr(exc)))
        try:
            if MARKER.exists():MARKER.unlink()
        except Exception as exc:cleanup.append(dict(operation='remove_marker',error=repr(exc)))
        if cleanup:
            path=BASE/(PREFIX+'_interruption.json')
            data=read(path) if path.exists() else dict(complete=False,error='Cleanup failed',phase='cleanup',last_step=step,completed_arms=len(outcomes))
            data['cleanup_errors']=cleanup;path.write_text(json.dumps(data,indent=2)+'\n')
            raise RuntimeError('V10 cleanup failed: '+json.dumps(cleanup))
    try:call(sys.executable,'scripts/v10_audit_epoch_dev.py')
    except Exception as exc:
        write(BASE/(PREFIX+'_interruption.json'),dict(complete=False,error=repr(exc),phase='terminal_audit',last_step=step,completed_arms=len(outcomes)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');a=p.parse_args()
    if a.plan:print(json.dumps(dict(status='Prepared18-armdevelopment; execution requires new seal and all prerequisite results',actions=build_plan()),indent=2))
    else:execute()
