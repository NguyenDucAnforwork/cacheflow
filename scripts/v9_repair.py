"""Prospective native-bookkeeping intervention, never a primary performance study."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import httpx
import psutil
import yaml
from v6_raw_archive import sha
from v6_regenerate_full_inputs import wait_parent,idle,SERVICES
from v8_diag3 import idle_gpu
from v8_diagnostic_capture import write
from v8_observe_lookup_watermark import inflated_snapshots
from v7_observe_full_liveness import parsed_lines
from v9_native_identity import expected,SOURCE
from v9_repair_capture import capture,capture_source

BASE=Path('results/v3');PREFIX='v9repair1';REG=BASE/(PREFIX+'_registration.json');PROTOCOL=Path('docs/V9_NATIVE_WATERMARK_INTERVENTION.md')
PARENT=BASE/'v8diag3_registration.json';CONFIGS={n:Path('/etc/supervisor/conf.d/'+n+'.conf') for n in ['cacheflow_v2_gateway','cacheflow_v2_vllm']}


def plan():
    sequence=[('probe','reference',101),('probe','idempotent',101),('full','reference',901),('full','idempotent',901),('full','idempotent',902),('full','reference',902)]
    result=[]
    for stage,mode,seed in sequence:
        rid=f'{PREFIX}-{stage}-{mode}-s{seed}'
        result.append(dict(run_id=rid,stage=stage,mode=mode,seed=seed,probe=stage=='probe',proof_label=rid+'-native',probe_label=rid+'-probe',policy='packing_reuse',
            trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl' if stage=='probe' else f'data/processed/v3/v5-full4b-qps4-s{seed}.jsonl.gz',requests=60 if stage=='probe' else 1986))
    return result


def original_terminal():
    for p in psutil.process_iter(['cmdline','status']):
        argv=p.info['cmdline'] or []
        assert p.info['status']==psutil.STATUS_ZOMBIE or not ('scripts/v8_diag3.py' in argv and 'execute' in argv),'V8 controller still live'


def register(pid=None):
    assert not REG.exists();parent=json.loads(PARENT.read_text())
    if pid is not None:
        p=psutil.Process(pid);argv=p.cmdline();assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE and argv[-2:]==['scripts/v8_diag3.py','execute']
        dependency=dict(wait_mode='live_exact_parent',after_pid=pid,after_create_time=p.create_time(),after_argv=argv)
    else:
        original_terminal();idle_gpu();terminal=BASE/'v8diag3_terminal.json';t=json.loads(terminal.read_text());assert t['diagnostic_execution_complete'] is True
        dependency=dict(wait_mode='already_terminal_verified_process_scan',terminal_sha256=sha(terminal))
    evidence=[PARENT,BASE/'v8diag1_offA_postmortem_integrity.json',BASE/'v6full1_union_s902_terminal_failure.json',
        BASE/'v8diag3_live_lookup_watermark_01.json',BASE/'v8diag3_observed_store_metadata_replay_01.json',
        BASE/'v8_epoch_trace_revision_registration.result.json',BASE/'v6full1_input_regeneration_registration.result.json']
    sources=parent['source_sha256']|{n:sha(n) for n in ['src/cacheflow/v9_lookup_watermark.py','src/cacheflow/v8_liveness_probe.py',
        'scripts/v9_native_hooks/sitecustomize.py','scripts/v9_serve_vllm.sh','scripts/v9_native_identity.py','scripts/v9_repair_capture.py','scripts/v9_repair.py',
        'scripts/v8_observe_lookup_watermark.py','scripts/v6_main_resources.py','scripts/v2_quality_audit.py','scripts/v9_audit_repair.py']}
    for n,h in sources.items():assert sha(n)==h,n
    r=dict(kind='native_watermark_repair_diagnostic_not_epoch_or_primary_study',registered_utc=datetime.now(timezone.utc).isoformat(),**dependency,
        parent_registration_sha256=sha(PARENT),protocol_sha256=sha(PROTOCOL),actions=plan(),source_sha256=sources,
        native_source_sha256=parent['native_source_sha256'],native_method_expected=expected(),capture_transformation=capture_source()[1],
        model_artifact_sha256=parent['model_artifact_sha256'],main_package_versions=parent['main_package_versions'],
        input_sha256={str(n):sha(n) for n in {Path(s['trace']) for s in plan()}|{Path(s['trace']).with_suffix('.manifest.json') for s in plan()}},config_original=parent['config_original'],
        evidence_sha256={str(p):sha(p) for p in evidence},evaluator_sha256=sha('data/processed/v2/evaluator/evaluation.py'),
        scope='6fresh engines:2profiled60QA native reference/idempotent checks, then4unprofiled1986QA reference/idempotent pairs at901/902 in reversed order.360separatewarmups;8064targets.600s diagnostic timeouts, no retries. One native lookup statement only, no epoch or HOL patch. All outcomes diagnostic; actual quality/source work and constructor code identity retained. Strongbaseline/fullprimary confirmation remains required.')
    manifest902=Path('data/processed/v3/v5-full4b-qps4-s902.jsonl.gz').with_suffix('.manifest.json');assert manifest902.is_file()
    frozen=json.loads((BASE/'v6full1_freeze.json').read_text())
    for s in plan():
        if s['stage']=='full':assert sha(s['trace'])==frozen['input_file_sha256'][s['trace']]
    for step in r['actions']:
        assert not list(BASE.glob(step['run_id']+'.*')) and not list((BASE/'raw').glob(step['run_id']+'.*'))
    write(REG,r);return r


def verify(r,weights=False):
    assert r['kind']=='native_watermark_repair_diagnostic_not_epoch_or_primary_study' and r['actions']==plan()
    assert sha(PROTOCOL)==r['protocol_sha256'] and sha(PARENT)==r['parent_registration_sha256']
    for group in ['source_sha256','native_source_sha256','evidence_sha256']:
        for name,digest in r[group].items():assert sha(name)==digest,(group,name)
    assert expected()==r['native_method_expected'] and capture_source()[1]==r['capture_transformation']
    if weights:
        import importlib.metadata
        idle_gpu()
        for name,version in r['main_package_versions'].items():assert importlib.metadata.version(name)==version,name
        for group in ['model_artifact_sha256','input_sha256']:
            for name,digest in r[group].items():assert sha(name)==digest,name
    assert sha('data/processed/v2/evaluator/evaluation.py')==r['evaluator_sha256']


def probe_audit(step,r):
    files=sorted((BASE/'raw').glob(step['probe_label']+'.*.jsonl'));assert files
    rows=[]
    for path in files:rows.extend(parsed_lines(path.read_bytes()))
    assert not any(row['kind']=='probe_error' for row in rows)
    ready={row['target'] for row in rows if row['kind']=='hook_ready'};assert ready=={'scheduler','allocator','connector','worker'}
    for row in rows:
        if row['kind']=='hook_ready':assert row['source_sha256']==r['native_source_sha256'][row['source_path']]
    counts=Counter(row['kind'] for row in rows);assert all(counts[k]>0 for k in ['scheduler','connector_metadata','connector_worker'])
    eligible=sum(1 for row in rows if row['kind']=='connector_metadata' for t in row['tracker_states'].values()
        if t['state']=='PREFETCHING' and t['num_scheduled_tokens']==0 and sum(t['allocated_blocks_per_group'].values())==0 and t['lmcache_hit_tokens']>0)
    inflation=inflated_snapshots(rows)
    return dict(eligible_sampled_prefetch_states=eligible,distinct_inflated_ids=len(inflation),first_inflation_examples=inflation[:5],counts=dict(counts),
        raw_sha256={str(path):sha(path) for path in files},scope='Sampled native metadata across separate warm/target; counts are not total incidence, uniqueQA, STOREbytes, DMA or speed.')


def stop_services(call):
    from v4_services import service_pid
    errors=[]
    for name in SERVICES:
        try:
            if service_pid(name):call('supervisorctl','stop',name)
        except Exception as exc:errors.append(dict(service=name,error=repr(exc)))
    if errors:raise RuntimeError(json.dumps(errors))


def execute():
    r=json.loads(REG.read_text());out=BASE/(PREFIX+'_terminal.json');assert not out.exists() and not (BASE/(PREFIX+'_failure.json')).exists()
    if r['wait_mode']=='live_exact_parent':wait_parent(r)
    original_terminal();idle_gpu();verify(r)
    parent_path=BASE/'v8diag3_terminal.json';parent=json.loads(parent_path.read_text());assert parent['diagnostic_execution_complete'] is True and parent['cleanup_errors']==[] and len(parent['outcomes'])==4
    if r['wait_mode']!='live_exact_parent':assert sha(parent_path)==r['terminal_sha256']
    for n,p in CONFIGS.items():assert p.read_text()==r['config_original'][n],n
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='600',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='600',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    def call(*args):subprocess.run(list(map(str,args)),check=True,env=env)
    def runtime(*args):
        call(sys.executable,'scripts/v6_runtime.py',*args);path=Path('.cacheflow-v3-gateway.yaml');cfg=yaml.safe_load(path.read_text());cfg['http_read_timeout_s']=600;path.write_text(yaml.safe_dump(cfg,sort_keys=True))
    def gateway_ready():
        for _ in range(120):
            try:res=httpx.get('http://127.0.0.1:8100/health',timeout=2);res.raise_for_status();return
            except httpx.HTTPError:time.sleep(1)
        raise RuntimeError('Gateway readiness timeout')
    def update():call('supervisorctl','reread');call('supervisorctl','update','cacheflow_v2_vllm','cacheflow_v2_gateway')
    outcomes=[];error=None;cleanup=[];step=None
    try:
        for step in r['actions']:
            idle_gpu();verify(r,weights=True);assert shutil.disk_usage('.').free>=96*1024**2,'Insufficient disk; retain prior evidence'
            root=Path.cwd()
            for name,path in CONFIGS.items():
                text=r['config_original'][name]
                if name.endswith('gateway'):text=text.replace(f'command={root}/scripts/v2_serve_gateway.sh',f'command={root}/scripts/v6_serve_gateway.sh')
                else:
                    text=text.replace(f'command={root}/scripts/v2_serve_vllm.sh',f'command=/bin/bash {root}/scripts/v9_serve_vllm.sh')
                    fields=dict(CACHEFLOW_V9_WATERMARK_MODE=step['mode'],CACHEFLOW_V9_WATERMARK_PROOF=str(root/'results/v3/raw'/step['proof_label']),
                        CACHEFLOW_V9_EXPECTED_CONNECTOR_SHA=r['native_source_sha256'][str(SOURCE)],CACHEFLOW_V9_ENGINE_LOG=str(root/'results/v3/raw'/(step['run_id']+'.engine.log')),
                        CACHEFLOW_V9_ENABLE_PROBE=str(int(step['probe'])))
                    if step['probe']:fields['CACHEFLOW_V8_LIVENESS_LOG']=str(root/'results/v3/raw'/step['probe_label'])
                    text=text.replace('environment=','environment='+','.join(k+'="'+v+'"' for k,v in fields.items())+',',1)
                path.write_text(text)
            update()
            runtime('configure','--model','qwen3-4b','--max-inflight','64','--max-num-seqs','16','--cuda-graphs','--kv-capacity-tokens','43664',
                '--max-bypasses','8','--prepare-in-thread','--max-queue','512','--cpu-l1-bytes','48002236416','--upstream','http://127.0.0.1:8000')
            call('bash','scripts/v2_start.sh','B2','fifo','6')
            status=httpx.get('http://127.0.0.1:18080/status',timeout=5);status.raise_for_status();host=status.json()
            assert host['storage_manager']['l1_manager']['memory_total_bytes']==48049946624;write(BASE/(step['run_id']+'.host_status.json'),host)
            warm=dict(step,run_id=step['run_id']+'-warm',trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl',requests=60,policy='fifo')
            result=None
            for current in [warm,step]:
                runtime('gateway','--policy',current['policy'],'--max-inflight','64','--max-queue','512','--max-bypasses','8','--prepare-in-thread')
                call('supervisorctl','restart','cacheflow_v2_gateway');gateway_ready();call('bash','scripts/v2_reset.sh')
                print('V9 REPAIR DIAGNOSTIC',json.dumps(current),flush=True);record=capture(current,REG)
                if current is warm:assert record['errors']==0,'Warmup failure; retain and stop'
                else:result=record
            stop_services(call);verify(r)
            probe=probe_audit(step,r) if step['probe'] else None
            from v6_main_resources import analyze
            samples=parsed_lines((BASE/'raw'/(step['run_id']+'.metrics.jsonl')).read_bytes());resources=analyze(samples)
            quality_path=None
            if result['errors']==0:
                counters=resources['strict_counter_deltas']['vllm'];rows=parsed_lines((BASE/'raw'/(step['run_id']+'.jsonl')).read_bytes())
                assert counters['vllm:prompt_tokens_total']==sum(row['input_tokens'] for row in rows)
                assert counters['vllm:prompt_tokens_cached_total']+counters['vllm:request_prefill_kv_computed_tokens_sum']==counters['vllm:prompt_tokens_total']
                quality_path=BASE/(step['run_id']+'.quality.json');assert not quality_path.exists()
                call(sys.executable,'scripts/v2_quality_audit.py','--raw-dir',BASE/'raw','--run-ids',step['run_id'],'--output',quality_path)
            audit=dict(diagnostic_integrity_checked=True,performance_valid=False,step=step,result=result,probe=probe,resources=resources,
                quality_sha256=sha(quality_path) if quality_path else None,quality_not_scored_reason=None if quality_path else 'Failed whole workload; never grade successful subset as a complete run',
                registration_sha256=sha(REG),source_after_verified=True,scope='Intervention diagnostic only. All error records retained; actual official quality/source accounting only for complete successful targets. Sampled CPU/RSS/counters are not DMA time or a primary performance contrast.')
            ap=BASE/(step['run_id']+'.repair_audit.json');write(ap,audit);outcomes.append(dict(run_id=step['run_id'],errors=result['errors'],requests=result['requests'],audit_sha256=sha(ap)))
            write(BASE/(step['run_id']+'.outcome.json'),outcomes[-1])
            if step['stage']=='probe':
                assert probe['eligible_sampled_prefetch_states']>0,'No eligible preallocation sample; validation inconclusive'
                if step['mode']=='idempotent':assert probe['distinct_inflated_ids']==0,'Watermark inflation persists under correction'
                else:assert probe['distinct_inflated_ids']>0,'Reference positive control did not observe inflation'
    except Exception as exc:error=repr(exc)
    finally:
        try:stop_services(call)
        except Exception as exc:cleanup.append(dict(stage='stop',error=repr(exc)))
        for name,path in CONFIGS.items():
            try:path.write_text(r['config_original'][name])
            except Exception as exc:cleanup.append(dict(stage='restore',service=name,error=repr(exc)))
        try:update()
        except Exception as exc:cleanup.append(dict(stage='reload',error=repr(exc)))
    write(out,dict(diagnostic_execution_complete=error is None and not cleanup and len(outcomes)==6,error=error,cleanup_errors=cleanup,last_step=step,
        outcomes=outcomes,registration_sha256=sha(REG),performance_valid=False,scope='Repair diagnostic execution only; independent terminal audit/comparison, primary strongbaselines, epochGPU/controls/fullconfirmation and research completion remain required.'))
    if error or cleanup:raise RuntimeError(str(error)+' '+str(cleanup))
    call(sys.executable,'scripts/v9_audit_repair.py')


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('plan');c=sub.add_parser('register');c.add_argument('--after-pid',type=int);sub.add_parser('execute');a=p.parse_args()
    if a.command=='plan':print(json.dumps(dict(diagnostic_only=True,actions=plan()),indent=2))
    elif a.command=='register':register(a.after_pid);print('Registered native repair intervention',REG,flush=True)
    else:
        try:execute()
        except Exception as exc:
            path=BASE/(PREFIX+'_failure.json')
            if not path.exists():write(path,dict(complete=False,error=repr(exc),scope='Retained native repair failure; no implicit retry.'))
            raise
