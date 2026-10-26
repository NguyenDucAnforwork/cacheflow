"""Summarize native diagnostic states without inventing transfer/tensor correctness."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def summarize(rows):
    scheduler=[r for r in rows if r['kind']=='scheduler'];worker=[r for r in rows if r['kind']=='connector_worker']
    errors=[r for r in rows if r['kind']=='probe_error']
    result=dict(scheduler_snapshots=len(scheduler),worker_snapshots=len(worker),probe_errors=errors,
        both_native_components_observed=bool(scheduler and worker),
        max_duplicate_physical_blocks=None,min_free_blocks=None,blocked_snapshot_count=None,
        max_pending_store_futures=None,max_pending_retrieve_futures=None,near_full_blocked_states=[])
    if scheduler:
        result.update(max_duplicate_physical_blocks=max(r['duplicate_physical_blocks_above_one_per_expected_hash'] for r in scheduler),
            min_free_blocks=min(r['free_blocks'] for r in scheduler))
        blocked=[r for r in scheduler if r['running']==0 and r['waiting']+r['skipped_waiting']>0]
        result['blocked_snapshot_count']=len(blocked)
        result['near_full_blocked_states']=[dict(monotonic_ns=r['monotonic_ns'],pid=r['pid'],
            free_blocks=r['free_blocks'],total_blocks=r['total_blocks'],status_counts=r['status_counts'],
            duplicated_expected_prefix_hashes=r['duplicated_expected_prefix_hashes'],
            duplicate_physical_blocks_above_one_per_expected_hash=r['duplicate_physical_blocks_above_one_per_expected_hash'],
            request_states=[dict(request_id=q['request_id'],status=q['status'],num_computed_tokens=q['num_computed_tokens'],num_tokens=q['num_tokens'],
                allocated_blocks=sum(g['blocks'] for g in q['block_tables']),unhashed_blocks=sum(g['unhashed'] for g in q['block_tables'])) for q in r['requests']])
            for r in blocked if r['free_blocks']<=16]
    if worker:
        result['max_pending_store_futures']=max(r['state']['store_futures']['count'] for r in worker)
        result['max_pending_retrieve_futures']=max(r['state']['retrieve_futures']['count'] for r in worker)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--prefix',default='results/v3/raw/v5diag-stall1-probe');p.add_argument('--partial',action='store_true');p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    prefix=Path(a.prefix);paths=sorted(prefix.parent.glob(prefix.name+'.*.jsonl'));assert paths,'No native probe journals'
    rows=[];hashes={}
    for path in paths:
        blob=path.read_bytes();hashes[str(path)]=hashlib.sha256(blob).hexdigest();lines=blob.splitlines()
        for index,line in enumerate(lines):
            try:row=json.loads(line)
            except json.JSONDecodeError:
                assert a.partial and index==len(lines)-1,'Malformed completed probe journal'
                continue
            assert row['diagnostic_only'] is True;rows.append(row)
    rows.sort(key=lambda r:r['monotonic_ns'])
    result=dict(scope='Native instrumented liveness diagnostic snapshots only. Expected-prefix duplicate allocated blocks are not a tensor-content, successful-transfer or causal-deadlock proof. Point samples can miss transients. Results are not serving performance.',
        partial=a.partial,source_journal_sha256=hashes,**summarize(rows))
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print({k:v for k,v in result.items() if k not in ['source_journal_sha256','near_full_blocked_states','probe_errors']})


if __name__=='__main__':main()
