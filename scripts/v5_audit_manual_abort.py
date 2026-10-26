"""Audit retained client ledger after explicit manual abort; no performance table."""
import hashlib
import json
from collections import Counter
from pathlib import Path


def main():
    rid='v5r2-confirm-main-qps4-union64-s702';raw=Path('results/v3/raw')
    intervention=json.loads(Path('results/v3/v5r2_main_stall_manual_abort.json').read_text())
    assert intervention['run_id']==rid and intervention['natural_timeout'] is False
    data=(raw/f'{rid}.jsonl').read_bytes();rows=[json.loads(l) for l in data.splitlines()]
    summary=json.loads((raw/f'{rid}.summary.json').read_text());assert len(rows)==summary['requests']==40
    assert len({r['request_id'] for r in rows})==40 and summary['request_read_timeout_s']==3600
    outputs={r['request_id']:r for r in map(json.loads,(raw/f'{rid}.outputs.jsonl').read_text().splitlines())}
    assert outputs.keys()=={r['request_id'] for r in rows}
    assert all(hashlib.sha256(outputs[r['request_id']]['output'].encode()).hexdigest()==r['output_hash'] for r in rows)
    assert all(r['run_id']==rid and r['trace_sha256']==summary['trace_sha256'] for r in rows)
    succeeded=[r for r in rows if r['status']=='ok'];failed=[r for r in rows if r['status']!='ok']
    assert len(succeeded)==summary['successes']==27 and len(failed)==summary['errors']==13
    gateway=[json.loads(l) for l in (raw/f'{rid}.preabort_gateway.jsonl').read_text().splitlines()]
    assert len(gateway)==27 and {r['request_id'] for r in gateway}=={r['request_id'] for r in succeeded}
    groups=[]
    for group in sorted({r['sample_id'] for r in rows}):
        g=[r for r in rows if r['sample_id']==group]
        groups.append(dict(sample_id=group,attempts=len(g),retained_successes=sum(r['status']=='ok' for r in g),
            interrupted_request_ids=[r['request_id'] for r in g if r['status']!='ok']))
    result=dict(run_id=rid,status='Terminal manual-abort diagnostic, not natural3600s timeout or primary performance',
        attempts=40,retained_successes=27,interrupted=13,status_counts=dict(Counter(r['status'] for r in rows)),
        per_conversation=groups,client_raw_sha256=hashlib.sha256(data).hexdigest(),
        trace_sha256=summary['trace_sha256'],retained_output_hashes_verified=True,
        preabort_gateway_ledger_matches_completed_clients=True,
        complete_success_latency_quantiles=None,primary_success_rate=None,
        limitations='Raw summary emits successful-only percentiles by implementation; they are excluded here.13RemoteProtocolErrors follow controlled gateway stop, not proven spontaneous transport failures. Native duplicate-block/connector cause remains unproven. Whole27-run repeat stage and full benchmark are incomplete.')
    Path('results/v3/v5r2_main_manual_abort_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Retained all40client outcomes/output hashes;27successes13manual interruptions; no performance quantiles')


if __name__=='__main__':main()
