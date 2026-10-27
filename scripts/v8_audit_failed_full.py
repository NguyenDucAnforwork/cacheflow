"""Retain whole failed full workload; never publish successful-only quantiles."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from v6_raw_archive import sha
from v7_observe_full_liveness import parsed_lines, nonprogress_suffix, PROGRESS

BASE=Path('results/v3')
RID='v6full1-main-g6-union64-s902'


def check_records(rows,outputs,fingerprints,summary):
    by={r['request_id']:r for r in rows};texts={r['request_id']:r for r in outputs}
    expected={r['request_id']:r for r in fingerprints}
    assert len(by)==len(rows)==len(expected)==summary['requests']==1986
    assert len(texts)==len(outputs)==len(by) and by.keys()==texts.keys()==expected.keys()
    for rid,r in by.items():
        f=expected[rid];out=texts[rid]
        assert r['run_id']==out['run_id']==summary['run_id']
        assert r['status']==out['status'] and r['trace_sha256']==summary['trace_sha256']
        assert r['engine_request_id']==summary['run_id']+'-'+rid
        for key in ['sample_id','qa_index','input_tokens','prompt_sha256']:assert r[key]==f[key],(rid,key)
        assert hashlib.sha256(out['output'].encode()).hexdigest()==r['output_hash']
        assert r['scheduled_arrival_ns']<=r['client_send_ns']<=r['complete_ns']
        if r['first_token_ns'] is not None:assert r['client_send_ns']<=r['first_token_ns']<=r['complete_ns']
        if r['output_tokens'] is not None:assert 0<=r['output_tokens']<=f['max_tokens']==96
        if r['status']=='ok':assert r['server_prompt_tokens']==r['input_tokens'] and r['http_status']==200 and r['first_token_ns'] is not None
    statuses=Counter(r['status'] for r in rows)
    assert statuses['ok']==summary['successes'] and len(rows)-statuses['ok']==summary['errors']>0
    return dict(statuses)


def audit(output):
    output=Path(output);assert not output.exists()
    raw=BASE/'raw';freeze_path=BASE/'v6full1_freeze.json';freeze=json.loads(freeze_path.read_text())
    interruption=BASE/'v6full1_continuation_r1_interruption.json';inter=json.loads(interruption.read_text())
    assert inter['last_step']['run_id']==RID and inter['phase']=='measured' and inter['completed_arms']==10
    invalid=BASE/(RID+'.invalid');assert invalid.is_file()
    step=next(s for s in freeze['actions'] if s['run_id']==RID)
    preflight_path=BASE/'v6full1_input_preflight.json';pre=json.loads(preflight_path.read_text())
    fp_path=Path(pre['main_fingerprints_path']);assert sha(fp_path)==pre['main_fingerprints_sha256']
    assert freeze['preflight_artifact_sha256'][str(fp_path)]==sha(fp_path)
    summary_path=raw/(RID+'.summary.json');s=json.loads(summary_path.read_text())
    manifest_path=Path(step['trace']).with_suffix('.manifest.json');manifest=json.loads(manifest_path.read_text())
    assert s['trace_sha256']==manifest['trace_sha256'] and s['requests']==step['requests']
    assert s['request_read_timeout_s']==s['request_pool_timeout_s']==3600 and s['client_keepalive_connections']==0
    assert s['model_revision']==manifest['model_revision'] and s['gpu_kv_bytes']==6*(1<<30)
    paths=[raw/(RID+suffix) for suffix in ['.jsonl','.outputs.jsonl','.metrics.jsonl','.summary.json']]
    rows=parsed_lines(paths[0].read_bytes());outputs=parsed_lines(paths[1].read_bytes())
    statuses=check_records(rows,outputs,json.loads(fp_path.read_text())['requests'],s)
    samples=parsed_lines(paths[2].read_bytes());longest=[];current=[]
    # A terminal cancellation can change waiting/KV counters. Find the longest
    # exact no-progress interval, not only the last metric suffix.
    for sample in samples:
        m=sample['vllm'];signature=tuple(m.get(k) for k in PROGRESS+['vllm:num_requests_running','vllm:num_requests_waiting','vllm:kv_cache_usage_perc'])
        eligible=all(v is not None for v in signature) and m.get('vllm:num_requests_running')==0 and m.get('vllm:num_requests_waiting',0)>0 and sample['gpu'].get('gpu_util_pct')==0
        if not eligible:current=[];continue
        old=tuple(current[-1]['vllm'].get(k) for k in PROGRESS+['vllm:num_requests_running','vllm:num_requests_waiting','vllm:kv_cache_usage_perc']) if current else None
        current=current+[sample] if signature==old else [sample]
        if current[-1]['timestamp_ns']-current[0]['timestamp_ns']>(longest[-1]['timestamp_ns']-longest[0]['timestamp_ns'] if longest else -1):longest=current
    assert longest and len(nonprogress_suffix(longest))==len(longest)
    log=raw/'gateway.jsonl';blob=log.read_bytes();gateway=[r for r in parsed_lines(blob) if r.get('run_id')==RID]
    gate={r['request_id']:r for r in gateway};by={r['request_id']:r for r in rows}
    assert len(gate)==len(gateway) and gate.keys()<=by.keys()
    assert {r['request_id'] for r in rows if r['status']=='ok'}<=gate.keys()
    result=dict(kind='complete_record_integrity_check_of_failed_full_attempt',performance_valid=False,research_complete=False,
        run_id=RID,requests=len(rows),successes=s['successes'],errors=s['errors'],status_counts=statuses,
        completed_full_arms=10,failed_full_arms=1,unexecuted_full_arms=19,
        gateway_closed_records=len(gateway),gateway_status_counts=dict(Counter(r['status'] for r in gateway)),
        client_records_without_closed_gateway_record=len(by.keys()-gate.keys()),
        longest_exact_nonprogress_s=(longest[-1]['timestamp_ns']-longest[0]['timestamp_ns'])/1e9,
        first_nonprogress_sample=longest[0],last_nonprogress_sample=longest[-1],
        raw_sha256={str(p):sha(p) for p in paths},
        metadata_sha256={str(p):sha(p) for p in [freeze_path,interruption,invalid,preflight_path,fp_path,manifest_path,BASE/(RID+'.setup.json')]},
        global_gateway_prefix_bytes=len(blob),global_gateway_prefix_sha256=hashlib.sha256(blob).hexdigest(),
        auditor_source_sha256=sha(__file__),
        scope='All1986client records including failures and captured partial/empty outputs checked against sealed input fingerprints; no rerun, successful-only latency/quality comparison, native root-cause proof or complete30-arm claim. Client timeout types may be downstream consequences of engine nonprogress, not its cause. No lost gateway record is silently counted as a gateway success. Raw summary percentile fields are retained as original bytes but excluded from this failed-attempt report.')
    with output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['requests','successes','errors','status_counts','longest_exact_nonprogress_s']},indent=2))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();audit(a.output)
