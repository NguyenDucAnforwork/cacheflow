"""Audit matched same-engine native/gateway V4 dev comparisons."""
import hashlib
import json
import statistics
from pathlib import Path


def read(path):return [json.loads(l) for l in path.read_text().splitlines()]


def load(rid):
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    assert not (base/f'{rid}.invalid').exists()
    s=json.loads((raw/f'{rid}.summary.json').read_text());setup=json.loads((base/f'{rid}.setup.json').read_text())
    m=json.loads((base/f'{rid}.metrics_summary.json').read_text())['counter_deltas']
    requests=read(raw/f'{rid}.jsonl');outputs={x['request_id']:x for x in read(raw/f'{rid}.outputs.jsonl')}
    assert len(requests)==len(outputs)==s['requests']==s['successes'] and not s['errors']
    for r in requests:
        assert r['status']=='ok' and r['input_tokens']==r['server_prompt_tokens']
        assert hashlib.sha256(outputs[r['request_id']]['output'].encode()).hexdigest()==r['output_hash']
        assert r['output_tokens']<=s['output_tokens_budget']
    total=sum(x['input_tokens'] for x in requests)
    assert m['sglang:prompt_tokens_total']==total
    assert m['sglang:cached_tokens_total']+m['sglang:uncached_prompt_tokens_histogram_sum']==total
    return s,setup,m


quality={x['run_id']:x for x in json.loads(Path('results/v3/sglang/v4_gateway_dev_quality.json').read_text())['runs']}
rows=[];contrasts=[]
for seed in [101,102,103]:
    reference_id=f'v4-sg4b-fi-kernel-lpm16-dev3-qps4-s{seed}';reference,refsetup,refmetrics=load(reference_id)
    for policy in ['lpm','fifo','packing','packing_reuse']:
        rid=f'v4-sg4b-fi-kernel-{policy}16-dev3-qps4-s{seed}';s,setup,m=load(rid)
        for key in ['trace_sha256','model_revision','gpu_kv_bytes','output_tokens_budget','prompt_version','engine_pid']:
            assert s[key]==reference[key],key
        assert setup['server_config']==refsetup['server_config']
        rows.append(dict(run_id=rid,seed=seed,policy=policy,p50_ms=s['arrival_ttft_p50_ms'],
            p95_ms=s['arrival_ttft_p95_ms'],p99_ms=s['arrival_ttft_p99_ms'],
            native_host_promoted_tokens=m.get('sglang:load_back_tokens_total'),
            native_uncached_tokens=m['sglang:uncached_prompt_tokens_histogram_sum'],
            f1=quality[rid]['answerable_f1'],cap_hits=quality[rid]['output_budget_hits']))
        if policy!='lpm':
            contrasts.append(dict(seed=seed,policy=policy,
                p95_delta_pct=100*(s['arrival_ttft_p95_ms']/reference['arrival_ttft_p95_ms']-1),
                p99_delta_pct=100*(s['arrival_ttft_p99_ms']/reference['arrival_ttft_p99_ms']-1),
                quality_delta=quality[rid]['answerable_f1']-quality[reference_id]['answerable_f1']))
aggregate=[]
for policy in ['lpm','fifo','packing','packing_reuse']:
    group=[r for r in rows if r['policy']==policy]
    aggregate.append(dict(policy=policy,**{k:(statistics.mean(r[k] for r in group) if all(r[k] is not None for r in group) else None)
        for k in ['p50_ms','p95_ms','p99_ms','native_host_promoted_tokens','native_uncached_tokens','f1']}))
Path('results/v3/sglang/v4_gateway_dev_analysis.json').write_text(json.dumps(dict(
    scope='V4 dev only;60 unique QA repeated3 seeds; native HiCache source semantics preserved',
    requests=720,errors=0,runs=rows,contrasts=contrasts,aggregate=aggregate),indent=2)+'\n')
for x in aggregate:print(x)
