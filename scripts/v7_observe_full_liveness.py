"""Passive live nonprogress evidence; no reset, probe injection or quantiles."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import httpx
import psutil
from v4_services import service_pid
from v6_raw_archive import sha

PROGRESS=['vllm:prompt_tokens_total','vllm:request_prefill_kv_computed_tokens_sum',
    'vllm:prompt_tokens_source_external_kv_transfer_total','vllm:time_to_first_token_seconds_count']


def parsed_lines(blob):
    result=[];lines=blob.splitlines()
    for i,line in enumerate(lines):
        try:result.append(json.loads(line))
        except json.JSONDecodeError:assert i==len(lines)-1,'Malformed nonfinal ledger line'
    return result


def nonprogress_suffix(samples):
    def signature(r):
        m=r['vllm'];return tuple(m.get(k) for k in PROGRESS+['vllm:num_requests_running','vllm:num_requests_waiting','vllm:kv_cache_usage_perc'])
    def idle_wait(r):
        m=r['vllm'];return m.get('vllm:num_requests_running')==0 and m.get('vllm:num_requests_waiting',0)>0 and r['gpu'].get('gpu_util_pct')==0
    assert samples and all(v is not None for v in signature(samples[-1]))
    wanted=signature(samples[-1]);suffix=[]
    for r in reversed(samples):
        if not idle_wait(r) or signature(r)!=wanted:break
        suffix.append(r)
    return list(reversed(suffix))


def process_record(pid):
    p=psutil.Process(pid);assert p.is_running() and p.status()!=psutil.STATUS_ZOMBIE
    return dict(pid=pid,create_time=p.create_time(),argv=p.cmdline(),status=p.status(),threads=p.num_threads(),cpu_times=p.cpu_times()._asdict())


def observe(rid,engine_pid,output):
    base=Path('results/v3');output=Path(output);assert not output.exists()
    freeze=json.loads((base/'v6full1_freeze.json').read_text());outcome_path=base/'v6full1_continuation_r1_outcomes.json';outcomes=json.loads(outcome_path.read_text())['runs']
    step=freeze['actions'][len(outcomes)];assert step['run_id']==rid and step['engine']=='main'
    raw=base/'raw';assert not (raw/(rid+'.summary.json')).exists(),'Observation requires an unfinished replay'
    setup_path=base/(rid+'.setup.json');setup=json.loads(setup_path.read_text())
    assert service_pid('cacheflow_v2_vllm')==engine_pid
    engine=process_record(engine_pid);assert engine['argv']==setup['actual_engine_argv_list']
    metric_path=raw/(rid+'.metrics.jsonl');blob=metric_path.read_bytes();samples=parsed_lines(blob);suffix=nonprogress_suffix(samples)
    assert len(suffix)>=2 and (suffix[-1]['timestamp_ns']-suffix[0]['timestamp_ns'])/1e9>=120
    endpoints={}
    with httpx.Client(timeout=5) as client:
        for name,url in [('gateway','http://127.0.0.1:8100/health'),('lmcache','http://127.0.0.1:18080/status')]:
            start=time.monotonic_ns();r=client.get(url);r.raise_for_status();endpoints[name]=dict(start_ns=start,end_ns=time.monotonic_ns(),status=r.status_code,value=r.json())
    for name,digest in freeze['actor_sha256'].items():assert sha(name)==digest,name
    log_path=raw/'gateway.jsonl';log_blob=log_path.read_bytes();closed=[r for r in parsed_lines(log_blob) if r.get('run_id')==rid]
    lm=service_pid('cacheflow_v2_lmcache');gw=service_pid('cacheflow_v2_gateway');assert lm>0 and gw>0
    result=dict(kind='live_full_nonprogress_observation_not_terminal_failure',run_id=rid,step=step,observed_monotonic_ns=time.monotonic_ns(),
        freeze_sha256=sha(base/'v6full1_freeze.json'),outcomes_sha256=sha(outcome_path),setup_sha256=sha(setup_path),observer_source_sha256=sha(__file__),
        metric_prefix_sha256=hashlib.sha256(blob).hexdigest(),metric_prefix_bytes=len(blob),gateway_log_prefix_sha256=hashlib.sha256(log_blob).hexdigest(),gateway_log_prefix_bytes=len(log_blob),
        contiguous_no_progress_s=(suffix[-1]['timestamp_ns']-suffix[0]['timestamp_ns'])/1e9,samples=len(suffix),progress_keys=PROGRESS,first=suffix[0],last=suffix[-1],
        completed_gateway_records=len(closed),closed_status_counts={s:sum(r['status']==s for r in closed) for s in sorted({r['status'] for r in closed})},
        endpoints=endpoints,processes=dict(engine=engine,lmcache=process_record(lm),gateway=process_record(gw)),
        request_timeout_s=setup['gateway_before']['upstream_read_timeout_s'],
        scope='Existing metrics and read-only health/status GETs only. KV occupancy is recorded, not thresholded at99%. No reset/retry/signal/debugger/native probe/model hashing or serving-source/configuration change. No partial latency quantiles, terminal-failure claim, root-cause proof or assertion that healthy LMCache implies completed connector futures. Gateway completions are closed records, not all client successes. Original timeout remains unchanged.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print('Observed full nonprogress',round(result['contiguous_no_progress_s'],3),'seconds;',len(closed),'closed gateway records; no terminal claim',flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--engine-pid',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();observe(a.run_id,a.engine_pid,a.output)
