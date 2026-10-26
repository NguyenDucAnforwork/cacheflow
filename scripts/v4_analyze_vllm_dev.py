"""Summarize only the complete, audited18-arm V4 main-stack development matrix."""
import json
import statistics
from pathlib import Path

data=json.loads(Path('results/v3/v4_vllm_dev_audit.json').read_text())
quality={r['run_id']:r for r in json.loads(Path('results/v3/v4_vllm_dev_quality.json').read_text())['runs']}
assert data['requests']==1080 and data['errors']==0 and len(data['runs'])==18
rows={r['run_id']:r for r in data['runs']};aggregates=[];contrasts=[]
for arm in ['fifo16','fifo64','lpm_real16','bundle_wave16','dhas16','packing_reuse64']:
    group=[r for r in data['runs'] if r['arm']==arm]
    aggregates.append(dict(arm=arm,**{k:statistics.mean(r[k] for r in group)
        for k in ['p50_ms','p95_ms','p99_ms','computed_tokens','consumed_cpu_tokens']},
        f1=statistics.mean(quality[r['run_id']]['answerable_f1'] for r in group),
        budget_hits=sum(quality[r['run_id']]['output_budget_hits'] for r in group)))
for pair in data['pairs']:
    a=rows[pair['a']];b=rows[pair['b']]
    contrasts.append(dict(a=pair['a'],b=pair['b'],seed=a['seed'],
        **{k+'_delta_pct':100*(b[k]/a[k]-1) for k in ['p50_ms','p95_ms','p99_ms','consumed_cpu_tokens']},
        f1_delta=quality[pair['b']]['answerable_f1']-quality[pair['a']]['answerable_f1'],
        hash_mismatches=sum(not r['hash_equal'] for r in pair['paired_requests'])))
Path('results/v3/v4_vllm_dev_findings.json').write_text(json.dumps(dict(
    scope='Dev only;60 unique QA repeated3 arrival seeds; no individual-request independence assumption; CPU source tokens are not direct DMA bytes',
    aggregate=aggregates,paired_contrasts=contrasts),indent=2)+'\n')
for r in aggregates:print(r)
