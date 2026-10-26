"""Descriptive arrival-TTFT SLO attainment with failures in every denominator.

Thresholds are reporting points, not a new acceptance gate or timeout deadline.
Failed runs never receive successful-only latency quantiles from this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

THRESHOLDS_S=(1,5,10,30,60,300,600)


def summarize(rows,duration_s):
    assert rows and duration_s>0
    ok=[r for r in rows if r['status']=='ok']
    assert all(r['arrival_ttft_ms'] is not None and r['arrival_ttft_ms']>=0 for r in ok)
    success_fraction=len(ok)/len(rows)
    qos=[]
    for threshold in THRESHOLDS_S:
        count=sum(r['arrival_ttft_ms']<=threshold*1000 for r in ok)
        qos.append(dict(arrival_ttft_threshold_s=threshold,successful_within_threshold=count,
            fraction_of_all_attempts=count/len(rows),goodput_requests_per_s=count/duration_s))
    quantiles=None
    if len(ok)==len(rows):
        values=[r['arrival_ttft_ms'] for r in rows]
        quantiles={f'p{p}_ms':float(np.percentile(values,p)) for p in [50,95,99]}
    return dict(attempts=len(rows),successes=len(ok),errors=len(rows)-len(ok),success_fraction=success_fraction,
        complete_success_quantiles=quantiles,qos=qos)


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    native=Path(f'results/v3/sglang/{a.run_id}.setup.json').exists()
    raw=Path('results/v3/raw/sglang' if native else 'results/v3/raw')
    source=raw/f'{a.run_id}.jsonl';data=source.read_bytes();rows=[json.loads(l) for l in data.splitlines()]
    s=json.loads((raw/f'{a.run_id}.summary.json').read_text())
    assert len(rows)==len({r['request_id'] for r in rows})==s['requests']
    assert sum(r['status']!='ok' for r in rows)==s['errors']
    groups=[]
    for group in sorted({r['sample_id'] for r in rows}):
        selected=[r for r in rows if r['sample_id']==group]
        groups.append(dict(sample_id=group,median_prompt_tokens=float(np.median([r['input_tokens'] for r in selected])),
            **summarize(selected,s['duration_s'])))
    result=dict(run_id=a.run_id,prompt_version=s['prompt_version'],trace_sha256=s['trace_sha256'],
        request_file_sha256=hashlib.sha256(data).hexdigest(),
        scope='Descriptive scheduled-arrival TTFT thresholds, failures included in all attempt denominators. Failed runs/groups omit latency quantiles; SLO goodput uses the entire run duration. Not saturation throughput or a causal fairness guarantee.',
        **summarize(rows,s['duration_s']),per_conversation=groups)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(a.run_id,'all attempts',result['attempts'],'errors',result['errors'],'600s attainment',result['qos'][-1]['fraction_of_all_attempts'])


if __name__=='__main__':main()
