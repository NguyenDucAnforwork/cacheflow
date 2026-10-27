"""Independent per-run V10 configuration/identity/raw/quality/resource audit."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from cacheflow.v6_replay import load_trace
from v10_epoch_study import BASE,FREEZE,read,write,verify
from v7_epoch_contracts import base_configuration
from v7_gateway_identity import validate_replay_window
from v6_raw_archive import sha
from v6_native_metrics import summarize
from v3_analyze_runs import load as main_integrity
from v4_audit_sglang_runs import audit as native_integrity
from v6_main_resources import analyze as main_resources
from v6_native_resources import analyze as native_resources
from v5_analyze_decode import analyze as decode
from v5_analyze_histograms import analyze as histogram
from v6_analyze_fairness import analyze as fairness
from v5_analyze_waits import analyze as waits


def rows(path):return [json.loads(line) for line in Path(path).read_text().splitlines()]


def check_phase(step,freeze,parent,seal,*,warm=False):
    sg=step['engine']=='sg';rid=step['run_id']+('-warm' if warm else '')
    meta=BASE/'sglang' if sg else BASE;raw=BASE/'raw/sglang' if sg else BASE/'raw'
    assert not (meta/(rid+'.invalid')).exists(),rid
    s=read(raw/(rid+'.summary.json'));setup=read(meta/(rid+'.setup.json'));requests=rows(raw/(rid+'.jsonl'));outputs=rows(raw/(rid+'.outputs.jsonl'))
    assert s['run_id']==setup['run_id']==rid
    trace='data/processed/v3/v5-dev4b3-qps4-s101.jsonl' if warm else step['trace'];m=read(Path(trace).with_suffix('.manifest.json'))
    assert s['trace_sha256']==m['trace_sha256'] and m['renderer_sha256']==seal['source_sha256']['src/cacheflow/v5_prompt.py']
    expected={r.request_id:r for r in load_trace(Path(trace))};rr={r['request_id']:r for r in requests};oo={r['request_id']:r for r in outputs}
    assert len(rr)==len(requests)==len(outputs)==len(oo)==60 and rr.keys()==oo.keys()==expected.keys()
    for key,r in rr.items():
        assert r['run_id']==oo[key]['run_id']==rid and r['status']=='ok' and r['input_tokens']==r['server_prompt_tokens']==expected[key].input_tokens
        assert r['scheduled_arrival_ns']<=r['client_send_ns']<=r['first_token_ns']<=r['complete_ns']
        assert r['prompt_sha256']==hashlib.sha256(expected[key].prompt.encode()).hexdigest()
        assert 0<r['output_tokens']<=96 and hashlib.sha256(oo[key]['output'].encode()).hexdigest()==r['output_hash']
    entry=None if sg else read(meta/(rid+'.v7_entrypoint.json'))
    current=dict(step,run_id=rid)
    base_configuration(current,setup,s,entry,parent,seal,freeze,warm)
    metadata=[meta/(rid+suffix) for suffix in ['.setup.json','.metrics_summary.json','.itl_histogram.json']]
    policy=None if sg and warm else 'fifo' if warm else step['policy'];implementation='reference' if warm else step['implementation']
    if policy:
        if sg:before,after=setup['gateway_implementation_before'],setup['gateway_implementation_after']
        else:
            before=read(meta/(rid+'.v7_identity_before.json'));after=read(meta/(rid+'.v7_identity_after.json'));pair=read(meta/(rid+'.v7_identity_pair.json'))
            metadata += [meta/(rid+suffix) for suffix in ['.v7_identity_before.json','.v7_identity_after.json','.v7_identity_pair.json','.v7_entrypoint.json']]
            assert pair['complete_identity_pair'] is True and pair['request_file_sha256']==sha(raw/(rid+'.jsonl'))
            assert pair['before_sha256']==sha(meta/(rid+'.v7_identity_before.json')) and pair['after_sha256']==sha(meta/(rid+'.v7_identity_after.json'))
        validate_replay_window(before,after,requests)
        assert before['implementation_record']['implementation']==implementation and before['implementation_record']['policy']==policy
        assert before['gateway_pid']==(setup['gateway_runtime_entrypoint']['pid'] if sg else entry['gateway_pid'])
    if not sg:
        from v10_epoch_native import validate_identity
        native_path=meta/(rid+'.v10_native_identity.json');proof=read(native_path)
        assert proof['freeze_sha256']==sha(FREEZE) and proof['before']['engine_pid']==s['engine_pid']
        validate_identity(current,proof,requests,freeze)
        metadata.append(native_path)
    if sg and not warm:native_integrity(rid)
    elif sg:assert read(meta/(rid+'.metrics_summary.json'))['counter_deltas']['sglang:prompt_tokens_total']==sum(r['input_tokens'] for r in requests)
    else:main_integrity(rid)
    samples=rows(raw/(rid+'.metrics.jsonl'));resource=native_resources(samples) if sg else main_resources(samples)
    files=[raw/(rid+suffix) for suffix in ['.jsonl','.outputs.jsonl','.summary.json','.metrics.jsonl']]
    if policy:files.append(raw/(rid+'.gateway.jsonl'))
    return s,setup,requests,resource,files,metadata


def audit_run(run_id,*,publish=True):
    parent,seal,f=verify();step=next(s for s in f['actions'] if s['run_id']==run_id);sg=step['engine']=='sg';meta=BASE/'sglang' if sg else BASE;raw=BASE/'raw/sglang' if sg else BASE/'raw'
    output=BASE/(run_id+'.v10_audit.json');assert not publish or not output.exists()
    warm=check_phase(step,f,parent,seal,warm=True);measured=check_phase(step,f,parent,seal)
    s,setup,requests,resource,files,metadata=measured
    assert warm[0]['engine_pid']==s['engine_pid'] and warm[0].get('lmcache_pid')==s.get('lmcache_pid')
    snapfile=meta/(run_id+'.itl_histogram.json');snap=read(snapfile)
    assert snap['request_file_sha256']==sha(raw/(run_id+'.jsonl'))
    recalculated=summarize(run_id,snap['before'],snap['after'],requests,s,'sglang' if sg else 'vllm')
    assert recalculated['coverage_valid'] is True and snap['coverage_valid'] is True and not snap['coverage_failures']
    assert recalculated['native_itl_mean_ms']==snap['native_itl_mean_ms']
    qp=BASE/(run_id+'.v10_quality.json')
    if publish:
        assert not qp.exists();subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir',str(raw),'--run-ids',run_id,'--output',str(qp)],check=True)
    quality_document=read(qp);assert quality_document['evaluator_sha256']==f['analysis_source_sha256']['data/processed/v2/evaluator/evaluation.py']
    q=quality_document['runs'][0];assert q['answerable_n']==60 and len(q['per_request'])==60
    assert q['run_id']==run_id and q['trace_sha256']==s['trace_sha256'] and q['prompt_version']==s['prompt_version'] and q['protocol']=='p_qa'
    if sg:
        assert resource['host_capacity_tokens']*147456==f['expected_native_host_bytes']
        counters=resource['counter_deltas'];assert counters['sglang:prompt_tokens_total']==sum(r['input_tokens'] for r in requests)
        captured=read(meta/(run_id+'.metrics_summary.json'))['counter_deltas']
        for key in ['sglang:prompt_tokens_total','sglang:cached_tokens_total','sglang:uncached_prompt_tokens_histogram_sum']:assert counters[key] is not None and counters[key]==captured[key],key
        host=dict(actual_native_host_payload_bytes=resource['host_capacity_tokens']*147456)
    else:
        status=read(BASE/(run_id+'-host-status.json'));heap=status['storage_manager']['l1_manager']['memory_total_bytes'];assert heap==f['expected_main_heap_bytes']
        counters=resource['strict_counter_deltas']['vllm'];assert counters['vllm:prompt_tokens_total']==sum(r['input_tokens'] for r in requests)
        captured=read(meta/(run_id+'.metrics_summary.json'))['counter_deltas']['vllm']
        for key in ['vllm:prompt_tokens_total','vllm:prompt_tokens_cached_total','vllm:request_prefill_kv_computed_tokens_sum','vllm:prompt_tokens_source_external_kv_transfer_total']:assert counters[key] is not None and counters[key]==captured[key],key
        host=dict(actual_main_heap_bytes=heap,configured_payload_bytes=f['host_payload_bytes'])
    if not sg:
        proof=read(meta/(run_id+'.v10_native_identity.json'))
        files+= [Path(p) for p in proof['before']['proof_sha256']]
        files.append(BASE/'raw'/(run_id+'-engine.log'))
    result=dict(complete=True,step=step,run_id=run_id,freeze_sha256=sha(FREEZE),requests=60,errors=0,separate_warmup_requests=60,
        engine_pid=s['engine_pid'],lmcache_pid=s.get('lmcache_pid'),summary=s,quality=q,quality_sha256=sha(qp),
        setup_sha256=sha(meta/(run_id+'.setup.json')),warm_setup_sha256=sha(meta/(run_id+'-warm.setup.json')),
        metadata_sha256={str(p):sha(p) for p in warm[5]+metadata+([] if sg else [BASE/(run_id+'-host-status.json')])},
        gateway_decision_stats=(setup.get('gateway_after') or {}).get('decision_stats'),
        host=host,resource=resource,native_itl=histogram(snapfile),secondary=decode(run_id),fairness=fairness(run_id),
        waits=waits(dict(runs=[dict(run_id=run_id,requests=60)])),raw_sha256={str(p):sha(p) for p in warm[4]+files},
        scope='Complete development arm and separate warmup, not full1986QA, quality equivalence, production liveness or completed research.')
    if publish:write(output,result);print('V10 development arm audited',run_id,flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');a=p.parse_args();audit_run(a.run_id)
