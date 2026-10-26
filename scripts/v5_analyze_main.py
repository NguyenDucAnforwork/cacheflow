"""Summarize the complete audited V5 main dev matrix; no pooled QA inference."""
import hashlib
import json
import statistics
from pathlib import Path


def main():
    audit=json.loads(Path('results/v3/v5r2_validation_audit.json').read_text())
    assert audit['requests']==2820 and not audit['errors'] and len(audit['runs'])==57
    rows=[r for r in audit['runs'] if r['run_id'].startswith('v5r2-dev-main-qps4-')]
    assert len(rows)==18 and sum(r['requests'] for r in rows)==1080
    quality={r['run_id']:r for r in json.loads(Path('results/v3/v5r2_validation_main_quality.json').read_text())['runs']}
    source_keys=dict(computed_tokens='vllm:request_prefill_kv_computed_tokens_sum',
        consumed_cpu_tokens='vllm:prompt_tokens_source_external_kv_transfer_total',
        gpu_source_tokens='vllm:prompt_tokens_source_local_cache_hit_total',preemptions='vllm:num_preemptions_total')
    for r in rows:
        tail=r['run_id'].split('-qps4-')[1];r['arm'],seed=tail.rsplit('-s',1);r['seed']=int(seed)
        r.update({k:r['source_counters'].get(v) for k,v in source_keys.items()})
        r['f1']=quality[r['run_id']]['answerable_f1'];r['output_budget_hits']=quality[r['run_id']]['output_budget_hits']
    by={r['run_id']:r for r in rows};aggregates=[];contrasts=[]
    arms=['fifo16','fifo64','lpm16','bundle16','dhas16','union64']
    for arm in arms:
        selected=[r for r in rows if r['arm']==arm];assert len(selected)==3
        def mean(key):
            values=[r[key] for r in selected]
            return statistics.mean(values) if all(v is not None for v in values) else None
        aggregates.append(dict(arm=arm,**{key:mean(key) for key in ['p50_ms','p95_ms','p99_ms',*source_keys,'f1']},
            output_budget_hits=sum(r['output_budget_hits'] for r in selected)))
    for seed in [101,102,103]:
        b=by[f'v5r2-dev-main-qps4-union64-s{seed}']
        for arm in arms[:-1]:
            a=by[f'v5r2-dev-main-qps4-{arm}-s{seed}']
            pair=next(p for p in audit['pairs'] if p['a']==a['run_id'] and p['b']==b['run_id'])
            contrasts.append(dict(a=a['run_id'],b=b['run_id'],seed=seed,
                **{key+'_delta_pct':100*(b[key]/a[key]-1) for key in ['p50_ms','p95_ms','p99_ms','consumed_cpu_tokens']},
                f1_delta=b['f1']-a['f1'],output_hash_mismatches=sum(not r['hash_equal'] for r in pair['paired_requests'])))
    result=dict(scope='Complete V5 revision2 main dev:60 unique QA repeated3 serving schedules,18 runs. Aggregate quantiles are means of run quantiles. Engine-consumed CPU tokens are not direct DMA bytes; nearby F1 means are not quality equivalence.',
        source_audit_sha256=hashlib.sha256(Path('results/v3/v5r2_validation_audit.json').read_bytes()).hexdigest(),
        requests=1080,errors=0,aggregate=aggregates,runs=rows,paired_contrasts=contrasts)
    Path('results/v3/v5r2_main_dev_findings.json').write_text(json.dumps(result,indent=2)+'\n')
    for r in aggregates:print(r)


if __name__=='__main__':main()
