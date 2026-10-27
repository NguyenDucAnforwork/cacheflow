"""Read-only V8 diagnostic evidence, never successful-only performance tables."""
import argparse
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
import httpx
import psutil
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines,PROGRESS,process_record

BASE=Path('results/v3');RAW=BASE/'raw';REG=BASE/'v8diag1_registration.json'
SIGNATURE=PROGRESS+['vllm:num_requests_running','vllm:num_requests_waiting','vllm:kv_cache_usage_perc']


def windows(samples):
    """Longest and trailing sampled interval; no fixed occupancy threshold."""
    longest=[];current=[];previous=None
    for row in samples:
        m=row['vllm'];signature=tuple(m.get(k) for k in SIGNATURE)
        eligible=all(v is not None for v in signature) and m['vllm:num_requests_running']==0 and m['vllm:num_requests_waiting']>0 and row['gpu'].get('gpu_util_pct')==0
        if not eligible:current=[];previous=None;continue
        current.append(row) if signature==previous else None
        if signature!=previous:current=[row]
        previous=signature
        if not longest or current[-1]['timestamp_ns']-current[0]['timestamp_ns']>longest[-1]['timestamp_ns']-longest[0]['timestamp_ns']:longest=current.copy()
    return longest,current


def describe_window(rows):
    if not rows:return None
    return dict(sample_count=len(rows),span_s=(rows[-1]['timestamp_ns']-rows[0]['timestamp_ns'])/1e9,
        max_sample_gap_s=max([(b['timestamp_ns']-a['timestamp_ns'])/1e9 for a,b in zip(rows,rows[1:])] or [0]),first=rows[0],last=rows[-1])


def cohort(gateway,start,end):
    result=[r for r in gateway if r['dispatch_ns']<=start and r['complete_ns']>=end]
    return dict(count=len(result),prefix_group_counts=dict(Counter(r['prefix_group'] for r in result)),
        requests=[{k:r.get(k) for k in ['request_id','input_tokens','prefix_group','dispatch_ns','first_token_ns','complete_ns','reserved_active_tokens','dispatch_reason','status']} for r in sorted(result,key=lambda r:r['dispatch_ns'])],
        scope='Closed gateway records whose recorded dispatch/complete intervals span the entire sampled window; not native block tables or recovered condition-lock ordering. Live in-flight records may not be closed yet.')


def native_window(journals,start,end):
    rows=[r for r in journals if start<=r['monotonic_ns']<=end]
    by={kind:[r for r in rows if r['kind']==kind] for kind in ['scheduler','allocation_failure','connector_metadata','connector_worker','probe_error']}
    scheduler=by['scheduler'];failures=by['allocation_failure'];worker=by['connector_worker']
    return dict(sampled_kind_counts={k:len(v) for k,v in by.items()},
        allocation_failures_by_request=dict(Counter(r['request_id'] for r in failures)),last_allocation_failures=failures[-12:],
        last_scheduler_snapshot=scheduler[-1] if scheduler else None,last_worker_snapshot=worker[-1] if worker else None,
        last_connector_snapshot=by['connector_metadata'][-1] if by['connector_metadata'] else None,
        scheduler_status_samples=dict(Counter(status for row in scheduler for status in row['status_counts'])),
        max_observed_duplicate_physical_blocks=max([r['duplicate_physical_blocks_above_one_per_expected_hash'] for r in scheduler] or [0]),
        sampling_can_miss_transient_operations_or_finished_ids=True,
        scope='Observed metadata only, filtered by shared host monotonic clock. Snapshots are not atomic;2s throttling can omit transient operations/finish signals. Empty sampled memberships do not prove every async action completed, and allocated expected-prefix duplicates do not prove equal loaded tensors. No root-cause, tensor/DMA, mitigation or speedup conclusion is generated.')


def analyze(rid,output,live=False):
    output=Path(output);assert not output.exists()
    reg=json.loads(REG.read_text());step=next(s for s in reg['actions'] if s['run_id']==rid)
    setup_path=BASE/(rid+'.diagnostic_setup.json');setup=json.loads(setup_path.read_text());assert setup['step']==step and setup['registration_sha256']==sha(REG)
    metric_path=RAW/(rid+'.metrics.jsonl');blob=metric_path.read_bytes();samples=parsed_lines(blob);longest,trailing=windows(samples)
    assert longest and len(longest)>1,'No sampled no-progress interval to analyze'
    result=dict(kind='v8_readonly_sampled_liveness_evidence',run_id=rid,diagnostic_only=True,performance_valid=False,terminal_client_result=False,
        observer_source_sha256=sha(__file__),registration_sha256=sha(REG),setup_sha256=sha(setup_path),
        metric_prefix_bytes=len(blob),metric_prefix_sha256=hashlib.sha256(blob).hexdigest(),
        longest_sampled_no_progress=describe_window(longest),trailing_sampled_no_progress=describe_window(trailing),observed_monotonic_ns=time.monotonic_ns())
    summary_path=RAW/(rid+'.summary.json')
    if live:
        assert not summary_path.exists(),'Use terminal mode for completed replay'
        engine=process_record(setup['engine']['pid']);assert engine['create_time']==setup['engine']['birth'] and engine['argv']==setup['engine']['argv']
        replays=[p.info for p in psutil.process_iter(['pid','cmdline','create_time','status']) if 'cacheflow.v6_replay' in (p.info['cmdline'] or []) and rid in p.info['cmdline'] and p.info['status']!=psutil.STATUS_ZOMBIE]
        assert len(replays)==1,'Verify actual live replay, not a marker'
        result['live_processes']=dict(engine=engine,replay=replays[0]);endpoints={}
        for name,url in [('gateway','http://127.0.0.1:8100/health'),('lmcache','http://127.0.0.1:18080/status')]:
            start=time.monotonic_ns();response=httpx.get(url,timeout=5);response.raise_for_status()
            endpoints[name]=dict(start_ns=start,end_ns=time.monotonic_ns(),value=response.json())
        result['endpoints']=endpoints
    else:
        s=json.loads(summary_path.read_text());assert s['requests']==step['requests']
        result.update(terminal_client_result=True,client_outcome={k:s[k] for k in ['requests','successes','errors']},summary_sha256=sha(summary_path))
    log_path=RAW/'gateway.jsonl';log_blob=log_path.read_bytes();gate=[r for r in parsed_lines(log_blob) if r.get('run_id')==rid]
    result.update(global_gateway_prefix_bytes=len(log_blob),global_gateway_prefix_sha256=hashlib.sha256(log_blob).hexdigest(),
        closed_gateway_cohort=cohort(gate,longest[0]['timestamp_ns'],longest[-1]['timestamp_ns']))
    if step['probe']:
        native=[];identity=[]
        for path in sorted(RAW.glob('v8diag1-probe.*.jsonl')):
            data=path.read_bytes();rows=parsed_lines(data);native.extend(rows)
            identity.append(dict(path=str(path),prefix_bytes=len(data),prefix_sha256=hashlib.sha256(data).hexdigest()))
        assert native,'Missing journals in profiled phase'
        for row in native:
            if row['kind']=='hook_ready':assert reg['native_source_sha256'][row['source_path']]==row['source_sha256']
        result['native_journal_prefixes']=identity;result['native_in_longest_window']=native_window(native,longest[0]['timestamp_ns'],longest[-1]['timestamp_ns'])
    result['scope']='Read-only diagnostic evidence; no source/config changes, reset, retry, injected hook, extra future/event query, partial successful-only quantiles or root-cause/fix claim. Health snapshots occur after the metric prefix and are separately clocked.'
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(rid,'sampled no-progress',round(result['longest_sampled_no_progress']['span_s'],3),'seconds; terminal=',result['terminal_client_result'],flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('output',type=Path);p.add_argument('--live',action='store_true');a=p.parse_args();analyze(a.run_id,a.output,a.live)
