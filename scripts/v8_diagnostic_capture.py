"""Same V6 replay, separate diagnostic registry, failed requests retained.

No primary collectors/auditors are weakened. Gateway coverage is a subset when
pool timeouts never reach ingress; the full client ledger remains mandatory.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
import httpx
import psutil
from v4_services import service_pid
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines

BASE=Path('results/v3');RAW=BASE/'raw'


def write(path,value):
    with Path(path).open('x') as f:f.write(json.dumps(value,indent=2)+'\n')


def process(service):
    pid=service_pid(service);assert pid>0
    p=psutil.Process(pid)
    return dict(pid=pid,birth=p.create_time(),argv=p.cmdline(),env={k:v for k,v in p.environ().items() if k in ['CACHEFLOW_V8_LIVENESS_LOG','CACHEFLOW_VLLM_LIVENESS_LOG','VLLM_BATCH_INVARIANT','PYTHONHASHSEED']})


def health():
    r=httpx.get('http://127.0.0.1:8100/health',timeout=5);r.raise_for_status();return r.json()


def check_rows(rows,outputs,expected,run_id):
    by={r['request_id']:r for r in rows};texts={r['request_id']:r for r in outputs}
    assert len(by)==len(rows)==len(expected) and len(texts)==len(outputs)==len(expected)
    assert by.keys()==texts.keys()==expected.keys()
    for rid,r in by.items():
        f=expected[rid];out=texts[rid]
        assert r['run_id']==out['run_id']==run_id and r['status']==out['status']
        assert r['prompt_sha256']==f['prompt_sha256'] and r['input_tokens']==f['input_tokens']
        assert hashlib.sha256(out['output'].encode()).hexdigest()==r['output_hash']
        assert r['engine_request_id']==run_id+'-'+rid
        assert r['scheduled_arrival_ns']<=r['client_send_ns']<=r['complete_ns']
        if r['output_tokens'] is not None:assert 0<=r['output_tokens']<=96
        if r['status']=='ok':assert r['server_prompt_tokens']==r['input_tokens'] and r['http_status']==200 and r['first_token_ns'] is not None
    return dict(Counter(r['status'] for r in rows))


def capture(step,registration_sha256):
    rid=step['run_id'];assert rid.startswith('v8diag1-')
    assert not list(BASE.glob(rid+'.*')) and not list(RAW.glob(rid+'.*'))
    before=health();assert before['active']==before['queue']==0
    engine=process('cacheflow_v2_vllm');lmcache=process('cacheflow_v2_lmcache');gateway=process('cacheflow_v2_gateway')
    assert 'cacheflow.v6_gateway:create_app' in gateway['argv']
    assert bool(engine['env'].get('CACHEFLOW_V8_LIVENESS_LOG'))==step['probe']
    assert not engine['env'].get('CACHEFLOW_VLLM_LIVENESS_LOG')
    def scalar(flag):
        positions=[i for i,v in enumerate(engine['argv']) if v==flag];assert positions,flag
        return engine['argv'][positions[-1]+1]
    assert int(scalar('--max-num-seqs'))==16 and int(scalar('--max-num-batched-tokens'))==8192
    assert int(scalar('--kv-cache-memory-bytes'))==6*(1<<30) and scalar('--dtype')=='bfloat16'
    assert '--enforce-eager' not in engine['argv'] and any('/1cfa9a7208912126459214e8b04321603b3df60c' in a for a in engine['argv'])
    assert '--l1-size-gb' in lmcache['argv']
    index=lmcache['argv'].index('--l1-size-gb')
    assert int(float(lmcache['argv'][index+1])*(1<<30))==48002236416
    runtime=json.loads(Path('.cacheflow-v3-runtime.json').read_text())
    assert runtime['max_num_seqs']==16 and runtime['max_num_batched_tokens']==8192 and runtime['cpu_l1_bytes']==48002236416
    assert before['upstream_read_timeout_s']==600 and int(Path('.cacheflow-v2-gpu-kv-bytes').read_text())==6*(1<<30)
    raw=RAW/(rid+'.jsonl');metrics=RAW/(rid+'.metrics.jsonl');gate=RAW/(rid+'.gateway.jsonl')
    # Mark all arms before requests, including both unprofiled controls.
    (BASE/(rid+'.invalid')).write_text('V8 liveness diagnostic only;600s timeouts. Excluded from all primary latency/quality comparisons, even if every request succeeds.\n')
    write(BASE/(rid+'.diagnostic_setup.json'),dict(step=step,engine=engine,lmcache=lmcache,gateway=gateway,runtime=runtime,
        gateway_config=Path('.cacheflow-v3-gateway.yaml').read_text(),gateway_before=before,registration_sha256=registration_sha256,
        capture_source_sha256=sha(__file__)))
    env=dict(os.environ,PYTHONPATH='src',CACHEFLOW_REQUEST_READ_TIMEOUT_S='600',CACHEFLOW_REQUEST_POOL_TIMEOUT_S='600',CACHEFLOW_CLIENT_KEEPALIVE_CONNECTIONS='0')
    collector=None
    with (RAW/(rid+'.collector.log')).open('x') as log:
        try:
            collector=subprocess.Popen([sys.executable,'-m','cacheflow.collect_metrics','--output',str(metrics)],env=env,stdout=log,stderr=subprocess.STDOUT)
            for _ in range(100):
                assert collector.poll() is None,'Metric collector exited'
                if metrics.exists() and metrics.stat().st_size:break
                time.sleep(.1)
            assert metrics.exists() and metrics.stat().st_size
            command=[sys.executable,'-m','cacheflow.v6_replay','--trace',step['trace'],'--url','http://127.0.0.1:8100',
                '--run-id',rid,'--output',str(raw),'--registry',str(BASE/'v8diag1_registry.csv'),'--metrics-path',str(metrics),
                '--mode','B2','--policy',step['policy'],'--gpu-kv-bytes',str(6*(1<<30)),'--engine-pid',str(engine['pid']),
                '--lmcache-pid',str(lmcache['pid']),'--engine-request-ids','--model-name','cacheflow-qwen3-4b',
                '--model-revision','1cfa9a7208912126459214e8b04321603b3df60c','--capture-text','--gateway-trace-path',str(gate)]
            # Replay stdout contains successful-only summary quantiles. Preserve
            # the original log privately; never use it as a diagnostic result.
            with (RAW/(rid+'.replay.log')).open('x') as replaylog:subprocess.run(command,check=True,env=env,stdout=replaylog,stderr=subprocess.STDOUT)
            time.sleep(2)
        finally:
            if collector is not None:
                if collector.poll() is None:collector.terminate()
                collector.wait(timeout=30)
    after=health()
    for name,old in [('cacheflow_v2_vllm',engine),('cacheflow_v2_lmcache',lmcache),('cacheflow_v2_gateway',gateway)]:
        now=process(name);assert now['pid']==old['pid'] and now['birth']==old['birth'] and now['argv']==old['argv']
    summary=json.loads(raw.with_suffix('.summary.json').read_text());rows=parsed_lines(raw.read_bytes());outputs=parsed_lines(raw.with_suffix('.outputs.jsonl').read_bytes())
    manifest=json.loads(Path(step['trace']).with_suffix('.manifest.json').read_text())
    assert summary['trace_sha256']==manifest['trace_sha256'] and summary['requests']==step['requests']
    assert summary['request_read_timeout_s']==summary['request_pool_timeout_s']==600 and summary['client_keepalive_connections']==0
    # Full fingerprints come from the sealed preparation. Warm fingerprints are
    # read from their actual trace without invoking a tokenizer or GPU.
    if step['requests']==1986:
        pre=json.loads((BASE/'v6full1_input_preflight.json').read_text());fp=Path(pre['main_fingerprints_path']);assert sha(fp)==pre['main_fingerprints_sha256']
        expected={r['request_id']:r for r in json.loads(fp.read_text())['requests']}
    else:
        expected={r['request_id']:dict(input_tokens=r['input_tokens'],prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest()) for r in parsed_lines(Path(step['trace']).read_bytes())}
    statuses=check_rows(rows,outputs,expected,rid)
    assert statuses.get('ok',0)==summary['successes'] and len(rows)-statuses.get('ok',0)==summary['errors']
    blob=(RAW/'gateway.jsonl').read_bytes();gateway_rows=[r for r in parsed_lines(blob) if r.get('run_id')==rid]
    ids={r['request_id'] for r in gateway_rows};assert len(ids)==len(gateway_rows) and ids<=expected.keys()
    assert {r['request_id'] for r in rows if r['status']=='ok'}<=ids
    with gate.open('x') as f:
        for row in gateway_rows:f.write(json.dumps(row,sort_keys=True)+'\n')
    files=[raw,raw.with_suffix('.outputs.jsonl'),raw.with_suffix('.summary.json'),metrics,gate]
    result=dict(diagnostic_integrity_checked=True,performance_valid=False,run_id=rid,requests=len(rows),successes=summary['successes'],errors=summary['errors'],
        status_counts=statuses,gateway_closed_records=len(gateway_rows),missing_closed_gateway_records=len(expected.keys()-ids),gateway_after=after,
        raw_sha256={str(p):sha(p) for p in files},global_gateway_prefix_bytes=len(blob),global_gateway_prefix_sha256=hashlib.sha256(blob).hexdigest(),
        setup_sha256=sha(BASE/(rid+'.diagnostic_setup.json')),registration_sha256=registration_sha256,
        scope='All client statuses/outputs retained; gateway subset explicitly counted. No official quality scoring, source-token reconciliation, primary-study completion, latency or speedup claim.')
    write(BASE/(rid+'.diagnostic_integrity.json'),result)
    print('V8 diagnostic',rid,len(rows),'requests',summary['errors'],'errors',flush=True)
    return result
