"""Prospective off/on/off after failed full attempt and all queued CPU jobs."""
import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
import httpx
import psutil
import yaml
from v4_services import service_pid
from v6_regenerate_full_inputs import wait_parent,idle,SERVICES
from v6_raw_archive import sha
from v6_freeze_full import ACTORS
from v8_diagnostic_capture import capture,write

ROOT=Path.cwd();BASE=Path('results/v3');PREFIX='v8diag1'
REG=BASE/(PREFIX+'_registration.json');PROTOCOL=Path('docs/V8_LIVENESS_DIAGNOSTIC_PROTOCOL.md')
CONFIGS={name:Path('/etc/supervisor/conf.d/'+name+'.conf') for name in ['cacheflow_v2_gateway','cacheflow_v2_vllm']}
PARENT=BASE/'v7dev1_epoch_after_trace_registration.json'
FAILURE=BASE/'v6full1_union_s902_terminal_failure.json'


def plan():
    return [dict(phase=phase,probe=phase=='on',run_id=f'{PREFIX}-{phase}-{label}',label=label,policy='fifo' if label=='warm' else 'packing_reuse',
        trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl' if label=='warm' else 'data/processed/v3/v5-full4b-qps4-s902.jsonl.gz',
        requests=60 if label=='warm' else 1986) for phase in ['offA','on','offB'] for label in ['warm','target']]


def sources():
    return sorted(set(ACTORS+['scripts/v8_full_liveness_diagnostic.py','scripts/v8_diagnostic_capture.py',
        'scripts/v8_serve_vllm_probe.sh','scripts/v8_vllm_probe_hooks/sitecustomize.py','src/cacheflow/v8_liveness_probe.py',
        'scripts/v8_audit_failed_full.py','scripts/v7_observe_full_liveness.py','scripts/v6_regenerate_full_inputs.py','scripts/v6_raw_archive.py']))


def workers_terminal():
    actors={'scripts/v6_continue_full_r1.py','scripts/v6_regenerate_full_inputs.py','scripts/v6_after_input_reproduction.py',
        'scripts/v7_epoch_cpu_probe.py','scripts/v7_epoch_trace_check.py','scripts/v7_after_epoch_trace.py'}
    for process in psutil.process_iter(['pid','cmdline','status']):
        assert process.info['status']==psutil.STATUS_ZOMBIE or not actors.intersection(process.info['cmdline'] or []),process.info


def register(pid=None):
    assert not REG.exists()
    if pid is not None:
        p=psutil.Process(pid)
        assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE
        assert p.cmdline()[-3:]==['scripts/v7_after_epoch_trace.py','execute',str(PARENT)]
        parent=dict(wait_mode='live_exact_parent',after_pid=pid,after_create_time=p.create_time(),after_argv=p.cmdline())
    else:
        workers_terminal();idle();assert PARENT.with_suffix('.failure.json').exists()
        parent=dict(wait_mode='already_terminal_verified_process_scan',parent_failure_sha256=sha(PARENT.with_suffix('.failure.json')))
    failed=json.loads(FAILURE.read_text());assert failed['errors']==1013 and failed['requests']==1986 and failed['performance_valid'] is False
    native=[row['path'] for name in ['v8_conditional_allocation_witness_v2.json','v8_conditional_lookup_watermark_witness.json'] for row in json.loads((BASE/name).read_text())['native_method_bodies']]
    native+=['/venv/main/lib/python3.12/site-packages/vllm/v1/core/sched/scheduler.py','/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/vllm_multi_process_adapter.py']
    reference=BASE/'v6full1_freeze.json';freeze=json.loads(reference.read_text())
    r=dict(kind='separate_full_seed902_liveness_off_on_off',registered_utc=datetime.now(timezone.utc).isoformat(),
        **parent,parent_registration_sha256=sha(PARENT),
        failure_sha256=sha(FAILURE),reference_freeze_sha256=sha(reference),actions=plan(),timeout_s=600,
        source_sha256={n:sha(n) for n in sources()},native_source_sha256={n:sha(n) for n in sorted(set(native))},
        model_artifact_sha256=freeze['model_artifact_sha256'],main_package_versions=freeze['main_package_versions'],protocol_sha256=sha(PROTOCOL),
        input_sha256={n:sha(n) for n in sorted({s['trace'] for s in plan()}|{str(Path(s['trace']).with_suffix('.manifest.json')) for s in plan()})},
        config_original={n:p.read_text() for n,p in CONFIGS.items()},
        scope='Separate diagnostic; original failed full run retained. Wait for exact last V7 waiter and all earlier CPU jobs to terminate, require its failure and idle services. Three fresh engines/CPU caches, same60warm then full1986seed902 per phase;600s uniform diagnostic timeouts, no retries/upstream patch. Profile middle only. No primary latency/quality comparison or completed research claim.')
    for n,s in r['config_original'].items():assert f'command={ROOT}/scripts/v2_serve_'+('gateway' if n.endswith('gateway') else 'vllm')+'.sh' in s
    write(REG,r);return r


def verify_pins(r):
    assert sha(PROTOCOL)==r['protocol_sha256'] and sha(FAILURE)==r['failure_sha256'] and sha(PARENT)==r['parent_registration_sha256']
    assert sha(BASE/'v6full1_freeze.json')==r['reference_freeze_sha256']
    for group in ['source_sha256','native_source_sha256']:
        for name,digest in r[group].items():assert sha(name)==digest,name


def probe_coverage(r):
    files=sorted((BASE/'raw').glob(PREFIX+'-probe.*.jsonl'));assert files,'No native journals'
    kinds={};ready=set();errors=[]
    for p in files:
        last=-1
        for line in p.read_text().splitlines():
            row=json.loads(line);assert row['diagnostic_only'] is True and row['monotonic_ns']>=last;last=row['monotonic_ns']
            kinds[row['kind']]=kinds.get(row['kind'],0)+1
            if row['kind']=='hook_ready':
                assert r['native_source_sha256'][row['source_path']]==row['source_sha256'];ready.add(row['target'])
            if row['kind']=='probe_error':errors.append(row)
    assert ready=={'scheduler','allocator','connector','worker'},ready
    assert all(kinds.get(k,0)>0 for k in ['scheduler','connector_metadata','connector_worker']),kinds
    assert not errors,errors[:4]
    return dict(kinds=kinds,ready=sorted(ready),journal_sha256={str(p):sha(p) for p in files},native_metadata_coverage_checked=True)


def execute():
    r=json.loads(REG.read_text());terminal=BASE/(PREFIX+'_terminal.json');assert not terminal.exists()
    if r.get('wait_mode','live_exact_parent')=='live_exact_parent':
        print('V8 diagnostic waiting on exact V7 waiter',r['after_pid'],flush=True);wait_parent(r)
    else:
        workers_terminal();assert sha(PARENT.with_suffix('.failure.json'))==r['parent_failure_sha256']
    idle();verify_pins(r)
    assert PARENT.with_suffix('.failure.json').exists(),'Preserve original V7 gate; no diagnosis override on success'
    workers_terminal()
    # Explicitly verify every earlier registered worker is terminal too.
    for name in ['v6full1_input_regeneration_registration.json','v6full1_r1_namespace_preparation_registration.json','v7_epoch_cpu_probe_registration.json','v7_epoch_trace_check_registration.json']:
        path=BASE/name;assert path.with_suffix('.result.json').exists() or path.with_suffix('.failure.json').exists(),name
    for n,p in CONFIGS.items():assert p.read_text()==r['config_original'][n],n
    outcomes=[];error=None;cleanup_errors=[];coverage=None
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='600',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='600',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    def call(*args):subprocess.run(list(map(str,args)),check=True,env=env)
    def stop():
        issues=[]
        for n in SERVICES:
            try:
                if service_pid(n):call('supervisorctl','stop',n)
            except Exception as exc:issues.append(dict(service=n,error=repr(exc)))
        if issues:raise RuntimeError(json.dumps(issues))
    def update():call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_gateway','cacheflow_v2_vllm')
    def runtime(*args):
        call(sys.executable,'scripts/v6_runtime.py',*args)
        p=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(p.read_text());cfg['http_read_timeout_s']=600;p.write_text(yaml.safe_dump(cfg,sort_keys=True))
    def wait_gateway():
        for _ in range(120):
            try:resp=httpx.get('http://127.0.0.1:8100/health',timeout=2);resp.raise_for_status();return
            except httpx.HTTPError:time.sleep(1)
        raise RuntimeError('Gateway readiness timeout')
    try:
        for phase in ['offA','on','offB']:
            idle();verify_pins(r)
            for name,version in r.get('main_package_versions',{}).items():assert importlib.metadata.version(name)==version,name
            assert shutil.disk_usage(ROOT).free>=96*1024**2,'Insufficient disk; retain previous evidence'
            for name,digest in r['input_sha256'].items():assert sha(name)==digest,name
            for name,digest in r['model_artifact_sha256'].items():assert sha(name)==digest,name
            for n,p in CONFIGS.items():
                content=r['config_original'][n]
                if n.endswith('gateway'):content=content.replace(f'command={ROOT}/scripts/v2_serve_gateway.sh',f'command={ROOT}/scripts/v6_serve_gateway.sh')
                elif phase=='on':
                    content=content.replace(f'command={ROOT}/scripts/v2_serve_vllm.sh',f'command=/bin/bash {ROOT}/scripts/v8_serve_vllm_probe.sh')
                    content=content.replace('environment=',f'environment=CACHEFLOW_V8_LIVENESS_LOG="{ROOT}/results/v3/raw/{PREFIX}-probe",',1)
                p.write_text(content)
            update()
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs',
                '--kv-capacity-tokens','43664','--max-bypasses','8','--prepare-in-thread','--max-queue','512','--cpu-l1-bytes','48002236416','--upstream','http://127.0.0.1:8000')
            call('bash','scripts/v2_start.sh','B2','fifo','6')
            for step in [s for s in r['actions'] if s['phase']==phase]:
                runtime('gateway','--policy',step['policy'],'--max-inflight','64','--max-queue','512','--max-bypasses','8','--prepare-in-thread')
                call('supervisorctl','restart','cacheflow_v2_gateway');wait_gateway();call('bash','scripts/v2_reset.sh')
                print('V8 DIAGNOSTIC',json.dumps(step),flush=True);result=capture(step,sha(REG));outcomes.append(result)
                # Expected target request timeouts are outcomes, not retry gates.
                if step['label']=='warm':assert result['errors']==0,'Warmup failure; no target after invalid preparation'
            stop()
            verify_pins(r)
            if phase=='on':coverage=probe_coverage(r)
    except Exception as exc:error=repr(exc)
    finally:
        try:stop()
        except Exception as exc:cleanup_errors.append(dict(stage='stop',error=repr(exc)))
        for n,p in CONFIGS.items():
            try:p.write_text(r['config_original'][n])
            except Exception as exc:cleanup_errors.append(dict(stage='restore_config',service=n,error=repr(exc)))
        try:update()
        except Exception as exc:cleanup_errors.append(dict(stage='reload_restored_config',error=repr(exc)))
    write(terminal,dict(diagnostic_execution_complete=error is None and not cleanup_errors and len(outcomes)==6,
        error=error,cleanup_errors=cleanup_errors,outcomes=outcomes,probe_coverage=coverage,registration_sha256=sha(REG),
        performance_valid=False,scope='Diagnostic coverage/counts only. Root-cause review and any serving fix require separate evidence/registration; all failures retained.'))
    if error or cleanup_errors:raise RuntimeError(str(error)+' '+str(cleanup_errors))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('plan');c=sub.add_parser('register');c.add_argument('--after-pid',type=int);sub.add_parser('execute');a=p.parse_args()
    if a.command=='plan':print(json.dumps(dict(diagnostic_only=True,timeout_s=600,actions=plan()),indent=2))
    elif a.command=='register':register(a.after_pid);print('Registered V8 diagnostic',REG,flush=True)
    else:
        try:execute()
        except Exception as exc:
            p=BASE/(PREFIX+'_failure.json')
            if not p.exists():write(p,dict(complete=False,error=repr(exc),scope='Retained failure; never silently retry.'))
            raise
