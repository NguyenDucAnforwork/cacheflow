"""Paired comparisons on one unchanged SG backend; no failed-only percentiles."""
import argparse
import json
import statistics
from pathlib import Path
import numpy as np
from v4_audit_sglang_runs import audit


def read(path):return [json.loads(l) for l in path.read_text().splitlines()]


def compare(a,b,quality):
    x=audit(a);y=audit(b)
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    sa=json.loads((base/f'{a}.setup.json').read_text());sb=json.loads((base/f'{b}.setup.json').read_text())
    for key in ['trace_sha256','model_revision','prompt_version','output_budget','runtime']:
        assert x[key]==y[key],key
    for key in ['server_config','launcher_pid','upstream_source_sha256']:
        assert sa[key]==sb[key],key
    assert not x['runtime']['profile_transfers']
    ra={r['request_id']:r for r in read(raw/f'{a}.jsonl')};rb={r['request_id']:r for r in read(raw/f'{b}.jsonl')}
    assert ra.keys()==rb.keys()
    assert all(ra[k]['prompt_sha256']==rb[k]['prompt_sha256'] for k in ra)
    qa=quality[a];qb=quality[b]
    assert qa['trace_sha256']==qb['trace_sha256']==x['trace_sha256']
    conversations=[]
    for group in sorted({r['sample_id'] for r in ra.values()}):
        aa=[r['arrival_ttft_ms'] for r in ra.values() if r['sample_id']==group]
        bb=[r['arrival_ttft_ms'] for r in rb.values() if r['sample_id']==group]
        conversations.append(dict(sample_id=group,a_mean_ms=statistics.mean(aa),b_mean_ms=statistics.mean(bb),
            a_p95_ms=float(np.percentile(aa,95)),b_p95_ms=float(np.percentile(bb,95))))
    return dict(a=a,b=b,requests=len(ra),trace_sha256=x['trace_sha256'],
        **{key+'_delta_pct':100*(y[key]/x[key]-1) for key in ['p50_ms','p95_ms','p99_ms']},
        a_latency_ms={k:x[k] for k in ['p50_ms','p95_ms','p99_ms']},
        b_latency_ms={k:y[k] for k in ['p50_ms','p95_ms','p99_ms']},
        a_uncached_tokens=x['native_uncached_tokens'],b_uncached_tokens=y['native_uncached_tokens'],
        a_host_promoted_tokens=x['native_host_promoted_tokens'],b_host_promoted_tokens=y['native_host_promoted_tokens'],
        a_f1=qa['answerable_f1'],b_f1=qb['answerable_f1'],f1_delta=qb['answerable_f1']-qa['answerable_f1'],
        a_cap_hits=qa['output_budget_hits'],b_cap_hits=qb['output_budget_hits'],
        output_hash_mismatches=sum(ra[k]['output_hash']!=rb[k]['output_hash'] for k in ra),
        per_conversation=conversations)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pairs',nargs='+',required=True)
    p.add_argument('--quality',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    quality={r['run_id']:r for r in json.loads(a.quality.read_text())['runs']}
    rows=[compare(*pair.split(':'),quality) for pair in a.pairs]
    a.output.write_text(json.dumps(dict(scope='Paired run-level dev contrasts; repeated QA are not independent new questions',pairs=rows),indent=2)+'\n')
    for r in rows:print(r['b'],*[round(r[k],3) for k in ['p50_ms_delta_pct','p95_ms_delta_pct','p99_ms_delta_pct','f1_delta']],r['output_hash_mismatches'])
