"""Preserve a terminal full-run failure as failure evidence, without latency wins."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    assert (base/f'{a.run_id}.invalid').exists(),'Require terminal invalidation, not a live run'
    summary=json.loads((raw/f'{a.run_id}.summary.json').read_text())
    assert summary['requests']==1986 and summary['errors']>0
    rows=[json.loads(l) for l in (raw/f'{a.run_id}.jsonl').read_text().splitlines()]
    assert len(rows)==len({r['request_id'] for r in rows})==1986
    assert sum(r['status']!='ok' for r in rows)==summary['errors']
    assert len({(r['sample_id'],r['qa_index']) for r in rows})==1986
    outputs={r['request_id']:r for r in map(json.loads,(raw/f'{a.run_id}.outputs.jsonl').read_text().splitlines())}
    assert len(outputs)==1986
    assert all(hashlib.sha256(outputs[r['request_id']]['output'].encode()).hexdigest()==r['output_hash'] for r in rows)
    by_status=collections.Counter(r['status'] for r in rows)
    failures=[r for r in rows if r['status']!='ok']
    result=dict(run_id=a.run_id,performance_valid=False,scope='All1986 attempted QA; errors retained. No success-only latency quantiles reported.',
        requests=1986,successes=summary['successes'],errors=summary['errors'],statuses=dict(by_status),
        duration_s=summary['duration_s'],trace_sha256=summary['trace_sha256'],
        model_revision=summary['model_revision'],prompt_version=summary['prompt_version'],
        invalid_reason=(base/f'{a.run_id}.invalid').read_text(),
        failure_completion_latency_ms_range=[min(r['latency_ms'] for r in failures),max(r['latency_ms'] for r in failures)],
        failed_http_status_counts=dict(collections.Counter(str(r['http_status']) for r in failures)),
        by_conversation={group:dict(requests=sum(r['sample_id']==group for r in rows),
            errors=sum(r['sample_id']==group and r['status']!='ok' for r in rows)) for group in sorted({r['sample_id'] for r in rows})},
        inference='PoolTimeout is a client connection-pool acquisition timeout, not an engine HTTP error. Other failures require separate diagnosis. This report preserves the failure without rerunning jobs or changing the method.')
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
