"""Reconstruct additive per-request arrival TTFT stages on one host clock.

Quantiles of stages do not add. Sum means or reconstruct each request first.
Upstream-to-token includes native queue, transfer, compute and transport; it is
never relabelled GPU compute time.
"""
import json
import statistics
from pathlib import Path
import numpy as np

p=Path('results/v3/v4_confirmation_audit.json');audit=json.loads(p.read_text());rows=[]
for run in audit['runs']:
    rid=run['run_id'];raw=Path('results/v3/raw/sglang' if '-sg-' in rid else 'results/v3/raw')
    gate=raw/f'{rid}.gateway.jsonl'
    if not gate.exists():continue
    requests={r['request_id']:r for r in map(json.loads,(raw/f'{rid}.jsonl').read_text().splitlines())}
    records=[]
    for g in map(json.loads,gate.read_text().splitlines()):
        r=requests[g['request_id']]
        assert g['arrival_ns']==r['scheduled_arrival_ns']
        points=[g['arrival_ns'],g['received_ns'],g['enqueue_ns'],g['dispatch_ns'],g['first_token_ns'],r['first_token_ns']]
        assert all(b>=a for a,b in zip(points,points[1:])),rid
        stages=dict(zip(['arrival_to_gateway','gateway_prepare','gateway_admission','upstream_to_token','return_stream'],
            [(b-a)/1e6 for a,b in zip(points,points[1:])]))
        assert abs(sum(stages.values())-r['arrival_ttft_ms'])<1e-6
        records.append(stages|dict(ttft=r['arrival_ttft_ms'],worker_queue=g['prepare_queue_ms'],worker_cpu=g['prepare_cpu_ms']))
    assert len(records)==run['requests']==40
    rows.append(dict(run_id=rid,requests=len(records),stages_ms={key:dict(mean=statistics.mean(r[key] for r in records),
        p50=float(np.percentile([r[key] for r in records],50)),p95=float(np.percentile([r[key] for r in records],95))) for key in records[0]}))
result=dict(scope='Frozen held-out gateway arms only,40QA/run. Stages add per request and in means, not in quantiles. Upstream stage includes native queue/transfer/compute/transport.',runs=rows)
Path('results/v3/v4_confirmation_waits.json').write_text(json.dumps(result,indent=2)+'\n')
for r in rows:
 print(r['run_id'],{k:round(v['mean'],2) for k,v in r['stages_ms'].items()})
