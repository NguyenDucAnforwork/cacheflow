"""Observed per-conversation waits and actual head bypasses, not liveness proof."""
import hashlib
import json
from pathlib import Path
import numpy as np
from v3_audit_admission import audit as admission


def analyze(run_id):
    sg=Path(f'results/v3/sglang/{run_id}.setup.json').exists()
    raw=Path('results/v3/raw/sglang' if sg else 'results/v3/raw')
    path=raw/(run_id+'.jsonl');blob=path.read_bytes();rows=[json.loads(l) for l in blob.splitlines()]
    summary=json.loads((raw/(run_id+'.summary.json')).read_text())
    assert len(rows)==summary['requests']==summary['successes'] and not summary['errors']
    assert len({r['request_id'] for r in rows})==len(rows) and all(r['status']=='ok' for r in rows)
    setup=json.loads(Path(f'results/v3/{"sglang/" if sg else ""}{run_id}.setup.json').read_text())
    gateway=None;by={}
    if not sg or setup['gateway_policy']:
        gateway=admission(run_id)
        if gateway['policy'] in {'packing_ready','ready_fifo'}:assert gateway['max_head_bypasses']<=gateway['configured_max_bypasses']==8
        by={r['request_id']:r for r in map(json.loads,(raw/(run_id+'.gateway.jsonl')).read_text().splitlines())}
        assert by.keys()=={r['request_id'] for r in rows}
        assert all(by[r['request_id']]['input_tokens']==r['input_tokens'] and by[r['request_id']]['status']=='ok' for r in rows)
    def quantiles(values):return dict(p50=float(np.percentile(values,50)),p95=float(np.percentile(values,95)),p99=float(np.percentile(values,99)),max=float(max(values)))
    groups=[]
    for sample_id in sorted({r['sample_id'] for r in rows}):
        rr=[r for r in rows if r['sample_id']==sample_id]
        item=dict(sample_id=sample_id,requests=len(rr),arrival_ttft_ms=quantiles([r['arrival_ttft_ms'] for r in rr]),
            completion_latency_ms=quantiles([(r['complete_ns']-r['scheduled_arrival_ns'])/1e6 for r in rr]))
        if by:
            gg=[by[r['request_id']] for r in rr]
            item.update(admission_wait_ms=quantiles([g['admission_wait_ms'] for g in gg]),
                preparation_ms=quantiles([g['ingress_prepare_ms'] for g in gg]),
                admission_deadline_overrun_requests=sum(g['admission_deadline_overrun_ms']>0 for g in gg))
        groups.append(item)
    return dict(run_id=run_id,request_file_sha256=hashlib.sha256(blob).hexdigest(),by_conversation=groups,admission=gateway,
        limitations='Completed requests only after complete-run success check. Per-conversation tails are descriptive, not normalized slowdown or population estimates. Max-bypass admission bound is not an E2E deadline or native progress guarantee; configured200ms is not a hard maximum queue wait. Observed completion does not prove production starvation freedom.')
