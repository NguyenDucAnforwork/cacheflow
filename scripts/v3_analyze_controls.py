"""Strict low-reuse control accounting; only eight distinct QA per run."""
import json
import statistics
from pathlib import Path
from v3_analyze_runs import load,compare

pairs=[]
for seed in [101,102,103]:
    a=load(f'v3-opt4b-fifo16-lowreuse8-qps4-s{seed}')
    b=load(f'v3-opt4b-packing_fifo16-lowreuse8-qps4-s{seed}')
    result=compare(a,b)
    result={k:v for k,v in result.items() if k not in ['a_metrics','b_metrics']}
    for run in [a,b]:
        assert run['metrics']['counter_deltas']['vllm']['vllm:prompt_tokens_source_external_kv_transfer_total']==0
    result['p99_delta_pct']=100*(b['summary']['arrival_ttft_p99_ms']/a['summary']['arrival_ttft_p99_ms']-1)
    pairs.append(result)
x=dict(scope='Low-reuse mechanism control;8 unique QA/contexts, repeated3 schedules, not a large tail benchmark',
    pairs=pairs,mean_p95_delta_pct=statistics.mean(x['p95_delta_pct'] for x in pairs),
    mean_p99_delta_pct=statistics.mean(x['p99_delta_pct'] for x in pairs),all_cpu_restored_tokens_zero=True)
Path('results/v3/opt4b_lowreuse_analysis.json').write_text(json.dumps(x,indent=2)+'\n')
print('p95 deltas',[r['p95_delta_pct'] for r in pairs]);print('mean',x['mean_p95_delta_pct'])
