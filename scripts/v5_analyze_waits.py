"""Reconstruct each V5 TTFT before summarizing stages; quantiles never add."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
import numpy as np


def stages(request,gateway):
    assert gateway['arrival_ns']==request['scheduled_arrival_ns']
    points=[gateway['arrival_ns'],gateway['received_ns'],gateway['enqueue_ns'],gateway['dispatch_ns'],gateway['first_token_ns'],request['first_token_ns']]
    assert all(b>=a for a,b in zip(points,points[1:]))
    result=dict(zip(['arrival_to_gateway','gateway_prepare','gateway_admission','upstream_to_token','return_stream'],[(b-a)/1e6 for a,b in zip(points,points[1:])]))
    assert abs(sum(result.values())-request['arrival_ttft_ms'])<1e-6
    return result|dict(ttft=request['arrival_ttft_ms'],worker_queue=gateway['prepare_queue_ms'],worker_cpu=gateway['prepare_cpu_ms'])


def analyze(audit):
    rows=[];skipped=[]
    for run in audit['runs']:
        rid=run['run_id'];sg=(Path('results/v3/sglang')/f'{rid}.setup.json').exists()
        base=Path('results/v3/sglang' if sg else 'results/v3');raw=Path('results/v3/raw/sglang' if sg else 'results/v3/raw')
        setup=json.loads((base/f'{rid}.setup.json').read_text())
        if sg and not setup['gateway_policy']:
            skipped.append(rid);continue
        summary=json.loads((raw/f'{rid}.summary.json').read_text())
        assert summary['requests']==summary['successes']==run['requests'] and not summary['errors']
        requests={r['request_id']:r for r in map(json.loads,(raw/f'{rid}.jsonl').read_text().splitlines())}
        gateways=[json.loads(l) for l in (raw/f'{rid}.gateway.jsonl').read_text().splitlines()]
        assert len(gateways)==len(requests)==run['requests']
        assert {g['request_id'] for g in gateways}==requests.keys()
        records=[stages(requests[g['request_id']],g) for g in gateways]
        rows.append(dict(run_id=rid,requests=len(records),stages_ms={key:dict(mean=statistics.mean(r[key] for r in records),
            p50=float(np.percentile([r[key] for r in records],50)),p95=float(np.percentile([r[key] for r in records],95))) for key in records[0]}))
    return dict(scope='Complete audited gateway arms. Stages add per request and in means, never in quantiles. Worker queue/CPU are already within prepare. Upstream-to-token includes engine queue, copy, compute and transport; not pure GPU time.',runs=rows,native_without_gateway=skipped)


def main():
    p=argparse.ArgumentParser();p.add_argument('audit',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    blob=a.audit.read_bytes();audit=json.loads(blob);assert not audit['errors']
    result=analyze(audit);result['source_audit_sha256']=hashlib.sha256(blob).hexdigest()
    a.output.write_text(json.dumps(result,indent=2)+'\n');print('Reconstructed',len(result['runs']),'gateway arms')


if __name__=='__main__':main()
