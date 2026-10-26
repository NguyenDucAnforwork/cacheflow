"""Compact held-out contrasts including all quality changes and fresh-process DFS."""
import json
from pathlib import Path
import numpy as np
from v4_verify_freeze import verify

freeze,digest=verify()
audit=json.loads(Path('results/v3/v4_confirmation_audit.json').read_text())
assert audit['method_freeze_sha256']==digest and len(audit['runs'])==27 and audit['requests']==1080
quality={}
for kind in ['sg','main']:
    quality.update({r['run_id']:r for r in json.loads(Path(f'results/v3/v4_confirmation_{kind}_quality.json').read_text())['runs']})
by={r['run_id']:r for r in audit['runs']}
pairs=[]
for kind,qpses,arms,candidate in [('sg',[4,2],['native','fifo','dfs'],'union'),('main',[4],['fifo64','bundle16'],'union64')]:
    for qps in qpses:
        for seed in [701,702,703]:
            for arm in arms:
                if kind=='sg' and qps==2 and arm!='native':continue
                prefix=f'v4c1-confirm-sg-lpm-qps{qps}' if kind=='sg' else f'v4c1-confirm-main-qps{qps}'
                a=f'{prefix}-{arm}-s{seed}';b=f'{prefix}-{candidate}-s{seed}'
                if arm=='dfs':a=f'v4c1-confirm-sg-dfs-qps{qps}-native-s{seed}'
                aa=by[a];bb=by[b];qa=quality[a];qb=quality[b]
                assert aa['requests']==bb['requests']==40
                qa_by={r['request_id']:r for r in qa['per_request']};qb_by={r['request_id']:r for r in qb['per_request']}
                assert qa_by.keys()==qb_by.keys() and qa['trace_sha256']==qb['trace_sha256']
                cats={}
                for c in sorted({r['category'] for r in qa_by.values()}):
                    ids=[k for k in qa_by if qa_by[k]['category']==c]
                    deltas=[qb_by[k]['score']-qa_by[k]['score'] for k in ids]
                    cats[str(c)]=dict(n=len(ids),mean_score_delta=float(np.mean(deltas)),
                        improved=sum(x>0 for x in deltas),worse=sum(x<0 for x in deltas),equal=sum(x==0 for x in deltas))
                raw=Path('results/v3/raw/sglang' if kind=='sg' else 'results/v3/raw')
                ar={r['request_id']:r for r in map(json.loads,(raw/f'{a}.jsonl').read_text().splitlines())}
                br={r['request_id']:r for r in map(json.loads,(raw/f'{b}.jsonl').read_text().splitlines())}
                assert ar.keys()==br.keys()==qa_by.keys()
                assert all(ar[k]['prompt_sha256']==br[k]['prompt_sha256'] for k in ar)
                pairs.append(dict(a=a,b=b,engine_kind=kind,qps=qps,seed=seed,
                    process_scope='fresh-process native policy competitor' if arm=='dfs' else 'unchanged engine process',
                    **{key+'_delta_pct':100*(bb[key]/aa[key]-1) for key in ['p50_ms','p95_ms','p99_ms']},
                    a_f1=qa['answerable_f1'],b_f1=qb['answerable_f1'],f1_delta=qb['answerable_f1']-qa['answerable_f1'],
                    a_output_budget_hits=qa['output_budget_hits'],b_output_budget_hits=qb['output_budget_hits'],
                    output_hash_mismatches=sum(ar[k]['output_hash']!=br[k]['output_hash'] for k in ar),categories=cats))
out=Path('results/v3/v4_confirmation_findings.json');out.write_text(json.dumps(dict(
    scope='40 unique held-out QA across three arrival schedules; no claim of120 independent questions or quality equivalence',
    method_freeze_sha256=digest,pairs=pairs),indent=2)+'\n')
for p in pairs:print(p['a'],round(p['p95_ms_delta_pct'],3),round(p['f1_delta'],6))
