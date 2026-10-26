"""Combine only the independently audited three primary development blocks."""
import json
import statistics
from pathlib import Path
from v6_freeze_full import sha
from v5_run_intervals import paired_log_interval


def read(path):return json.loads(Path(path).read_text())


def main():
    base=Path('results/v3/sglang');reg=read(base/'v6native1_registration.json');audits=[];traces=[]
    for seed in [101,102,103]:
        ap=base/f'v6native1_primary_s{seed}_checkpoint_audit.json';a=read(ap)
        assert a['completed_block'] and not a['overall_native_stage_complete'] and a['requests']==300 and a['errors']==0
        assert a['registration_sha256']==sha(base/'v6native1_registration.json')
        assert a['quality_sha256']==sha(base/f'v6native1_primary_s{seed}_checkpoint_quality.json')
        for row in a['runs']:
            assert row['setup_sha256']==sha(base/(row['run_id']+'.setup.json'))
            assert row['request_file_sha256']==sha(Path('results/v3/raw/sglang')/(row['run_id']+'.jsonl'))
        block=next(b for b in reg['blocks'] if b['regime']=='primary' and b['seed']==seed)
        assert len(a['runs'])==len(block['actions'])==5
        trace=Path(block['actions'][0]['trace']);assert sha(trace)==reg['trace_sha256'][str(trace)]
        rr=[json.loads(l) for l in trace.read_text().splitlines()]
        import hashlib
        traces.append({(r['sample_id'],r['qa_index']):hashlib.sha256(r['prompt'].encode()).hexdigest() for r in rr})
        audits.append((ap,a))
    assert traces[0]==traces[1]==traces[2] and len(traces[0])==60
    assert len({a['runs'][0]['engine_pid'] for _,a in audits})==3
    runs=[r for _,a in audits for r in a['runs']];by={r['run_id']:r for r in runs};aggregate=[]
    oraclepath=Path('results/v3/v6dev1_input_oracle.json');oracle=read(oraclepath);minimum=oracle['page16']['input_only_minimum_new_tokens']
    for arm in ['native','fifo64','union64','ready_fifo','packing_ready']:
        rr=[r for r in runs if r['arm']==arm];assert len(rr)==3
        aggregate.append(dict(arm=arm,**{k:statistics.mean(r[k] for r in rr) for k in ['p50_ms','p95_ms','p99_ms','computed_tokens','f1']},
            output_budget_hits=sum(r['output_budget_hits'] for r in rr),
            completion_p95_ms=statistics.mean(r['secondary']['completion_latency_ms']['p95'] for r in rr),
            client_tpot_proxy_p95_ms=statistics.mean(r['secondary']['client_tpot_proxy_ms']['p95'] for r in rr),
            observed_prefill_excess_over_input_only_page16=[r['computed_tokens']-minimum for r in rr],
            host_promoted_tokens=[r['host_promoted_tokens'] for r in rr],host_promotion_endpoints=[r['host_promotion_endpoints'] for r in rr]))
    pairs=[p|dict(seed=101+i) for i,(_,a) in enumerate(audits) for p in a['pairs']];intervals=[]
    for baseline,candidate in [('native','union64'),('native','packing_ready'),('union64','packing_ready'),('native','ready_fifo')]:
        pp=[p for p in pairs if p['baseline']==baseline and p['candidate']==candidate];assert len(pp)==3
        intervals.append(dict(baseline=baseline,candidate=candidate,metrics={key:paired_log_interval(
            [by[f'v6native1-primary-s{s}-{baseline}'][key] for s in [101,102,103]],
            [by[f'v6native1-primary-s{s}-{candidate}'][key] for s in [101,102,103]]) for key in ['p50_ms','p95_ms','p99_ms']}))
    result=dict(primary_complete=True,overall_native_stage_complete=False,requests=900,errors=0,separate_warmup_requests=180,
        source_audit_sha256={str(p):sha(p) for p,_ in audits},input_oracle_sha256=sha(oraclepath),
        scope='Three primary five-arm development blocks on60exposedQA; fresh native engine per seed, shared withinblock after flush/freshgateway. Means of run quantiles. Not the60-arm controls stage, full1986QA, a fresh semantic holdout or quality equivalence. Promotion deltas remain null when endpoint coverage is missing; static input-only reference is not native transient/publication/queue/transfer simulation.',
        aggregate=aggregate,runs=runs,pairs=pairs,exploratory_run_intervals=intervals)
    (base/'v6native1_primary_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in aggregate:print(r)
    for p in intervals:print(p['baseline'],p['candidate'],p['metrics']['p95_ms'])


if __name__=='__main__':main()
