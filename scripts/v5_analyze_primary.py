"""Audit the completed nine-arm primary SG dev block without waiting for controls."""
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from v5_verify import verify
from v4_audit_sglang_runs import audit
from v4_compare_sglang import compare


def main():
    parent,seal=verify();assert seal['revision']==2
    ids=[f'v5r2-dev-lpm-g6-qps4-{arm}-s{seed}' for seed in [101,102,103] for arm in ['native','fifo','union']]
    rows=[]
    for rid in ids:
        r=audit(rid);assert r['requests']==60 and r['prompt_version']=='locomo-qwen-concise-v5'
        s=json.loads(Path(f'results/v3/raw/sglang/{rid}.summary.json').read_text())
        assert s['client_keepalive_connections']==0 and s['request_read_timeout_s']==s['request_pool_timeout_s']==3600
        assert r['runtime']['same_batch_guard'] and not r['runtime']['profile_transfers']
        rows.append(r)
    out=Path('results/v3/v5r2_primary_sg_quality.json')
    subprocess.run([sys.executable,'scripts/v2_quality_audit.py','--raw-dir','results/v3/raw/sglang',
        '--run-ids',*ids,'--output',str(out)],check=True)
    quality={r['run_id']:r for r in json.loads(out.read_text())['runs']}
    pairs=[]
    for seed in [101,102,103]:
        for arm in ['native','fifo']:
            pairs.append(compare(f'v5r2-dev-lpm-g6-qps4-{arm}-s{seed}',f'v5r2-dev-lpm-g6-qps4-union-s{seed}',quality))
    aggregate=[]
    for arm in ['native','fifo','union']:
        selected=[r for r in rows if f'-{arm}-s' in r['run_id']]
        aggregate.append(dict(arm=arm,**{k:statistics.mean(r[k] for r in selected) for k in ['p50_ms','p95_ms','p99_ms']},
            f1=statistics.mean(quality[r['run_id']]['answerable_f1'] for r in selected)))
    result=dict(scope='V5 revision2 primary dev only:60 unique QA repeated3 arrival schedules; controls/main/repeats/full remain separate. Quantile means average run-level quantiles.',
        prompt_seal_sha256=hashlib.sha256(Path('results/v3/v5_prompt_freeze.json').read_bytes()).hexdigest(),
        requests=540,errors=0,runs=rows,pairs=pairs,aggregate=aggregate)
    Path('results/v3/v5r2_primary_sg_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    for p in pairs:print(p['a'],*[round(p[k],4) for k in ['p50_ms_delta_pct','p95_ms_delta_pct','p99_ms_delta_pct','f1_delta']])


if __name__=='__main__':main()
