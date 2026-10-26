"""Strict output/token audits and source-labelled latency tables for named SG runs."""
import argparse
import hashlib
import json
from pathlib import Path


def audit(rid):
    base=Path('results/v3/sglang');raw=Path('results/v3/raw/sglang')
    assert not (base/f'{rid}.invalid').exists(),rid
    summary=json.loads((raw/f'{rid}.summary.json').read_text())
    setup=json.loads((base/f'{rid}.setup.json').read_text())
    metrics=json.loads((base/f'{rid}.metrics_summary.json').read_text())['counter_deltas']
    rows=[json.loads(line) for line in (raw/f'{rid}.jsonl').read_text().splitlines()]
    outputs={r['request_id']:r for r in map(json.loads,(raw/f'{rid}.outputs.jsonl').read_text().splitlines())}
    ids=[r['request_id'] for r in rows]
    assert len(set(ids))==len(ids)==len(outputs)==summary['requests']==summary['successes']
    assert set(ids)==set(outputs) and not summary['errors']
    assert all(r['status']=='ok' and r['input_tokens']==r['server_prompt_tokens'] for r in rows)
    assert all(0<r['output_tokens']<=summary['output_tokens_budget'] for r in rows)
    assert all(hashlib.sha256(outputs[r['request_id']]['output'].encode()).hexdigest()==r['output_hash'] for r in rows)
    total=sum(r['input_tokens'] for r in rows)
    assert metrics['sglang:prompt_tokens_total']==total
    assert metrics['sglang:cached_tokens_total']+metrics['sglang:uncached_prompt_tokens_histogram_sum']==total
    if setup['gateway_policy']:
        state=setup['gateway_before']
        if state.get('decision_stats'):
            assert state['decision_stats']['calls']==0,'nonfresh gateway scheduler state'
        if setup.get('gateway_reset'):
            if 'completed_history_requests' in state:
                assert state['completed_history_requests']==0,'nonfresh prefix history'
            else:
                assert state.get('decision_stats',{}).get('calls')==0,'missing freshness evidence'
        from v3_audit_admission import audit as audit_admission
        admission=audit_admission(rid)
        assert setup['gateway_after']['active']==setup['gateway_after']['queue']==0
    else:admission=None
    return dict(run_id=rid,requests=len(rows),errors=0,trace_sha256=summary['trace_sha256'],
        model_revision=summary['model_revision'],prompt_version=summary['prompt_version'],
        gateway_policy=setup['gateway_policy'],
        gateway_prepare_mode=(setup.get('gateway_before') or {}).get('prepare_mode'),
        output_budget=summary['output_tokens_budget'],runtime=setup['runtime'],
        public_server_env=setup.get('public_server_env'),
        p50_ms=summary['arrival_ttft_p50_ms'],p95_ms=summary['arrival_ttft_p95_ms'],p99_ms=summary['arrival_ttft_p99_ms'],
        native_uncached_tokens=metrics['sglang:uncached_prompt_tokens_histogram_sum'],
        native_host_promoted_tokens=metrics.get('sglang:load_back_tokens_total'),admission=admission)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_ids',nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    runs=[audit(r) for r in a.run_ids]
    a.output.write_text(json.dumps(dict(scope='Named runs only; missing source counters remain null; profiling flags recorded',runs=runs),indent=2)+'\n')
    for r in runs:print(r['run_id'],r['requests'],*[round(r[k]/1000,3) for k in ['p50_ms','p95_ms','p99_ms']])
