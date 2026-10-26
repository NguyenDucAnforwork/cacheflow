"""Matched exploratory 4B dev results; no confirmation or quality-equivalence claim."""
import json
import statistics
from pathlib import Path

from v3_analyze_runs import compare,load

quality={x['run_id']:x for x in json.loads(Path('results/v3/opt4b_dev_quality.json').read_text())['runs']}
rows=[];pairs=[]
for seed in [101,102,103]:
    baseline=load(f'v3-opt4b-fifo16-dev3-qps4-s{seed}')
    for policy in ['fifo','lpm_real','bundle_wave','packing_fifo','dhas']:
        rid=f'v3-opt4b-{policy}16-dev3-qps4-s{seed}';run=load(rid)
        c=run['metrics']['counter_deltas']['vllm'];s=run['summary'];q=quality[rid]
        setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text())
        assert setup['runtime']['keepalive_connections']==0
        assert setup['runtime']['max_num_seqs']==16 and not setup['runtime']['enforce_eager']
        rows.append(dict(run_id=rid,seed=seed,policy=policy,p50_ms=s['arrival_ttft_p50_ms'],
            p95_ms=s['arrival_ttft_p95_ms'],p99_ms=s['arrival_ttft_p99_ms'],
            new_prefill=c['vllm:request_prefill_kv_computed_tokens_sum'],
            cpu_consumed_tokens=c['vllm:prompt_tokens_source_external_kv_transfer_total'],
            gpu_consumed_tokens=c['vllm:prompt_tokens_source_local_cache_hit_total'],
            preemptions=c['vllm:num_preemptions_total'],quality_f1=q['answerable_f1'],
            cap_hits=q['output_budget_hits'],decision_stats=setup['gateway_after'].get('decision_stats')))
        if policy!='fifo':
            result=compare(baseline,run)
            qs=quality[baseline['summary']['run_id']]
            result={k:v for k,v in result.items() if k not in ['a_metrics','b_metrics']}
            result['p99_delta_pct']=100*(s['arrival_ttft_p99_ms']/baseline['summary']['arrival_ttft_p99_ms']-1)
            result['quality_f1_delta']=q['answerable_f1']-qs['answerable_f1']
            pairs.append(result)
aggregate=[]
for policy in ['fifo','lpm_real','bundle_wave','packing_fifo','dhas']:
    group=[x for x in rows if x['policy']==policy]
    aggregate.append(dict(policy=policy,**{k:statistics.mean(x[k] for x in group)
        for k in ['p50_ms','p95_ms','p99_ms','cpu_consumed_tokens','new_prefill','quality_f1']}))
result=dict(scope='Dev only,60 unique QA repeated across3 arrival seeds; not fresh confirmation or whole LoCoMo',
    model='Qwen3-4B',requests=900,errors=0,runs=rows,contrasts=pairs,aggregate=aggregate)
Path('results/v3/opt4b_dev_analysis.json').write_text(json.dumps(result,indent=2)+'\n')
for x in aggregate:print(x)
