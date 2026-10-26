"""Reconstruct ingress queue/active intervals and actual head bypasses from raw logs."""
import argparse
import json
from collections import Counter
from pathlib import Path


def audit(run_id):
    path=Path('results/v3/raw')/f'{run_id}.gateway.jsonl'
    rows=[json.loads(l) for l in path.read_text().splitlines()]
    assert rows and all(r['status']=='ok' for r in rows)
    by={r['request_id']:r for r in rows};events=[]
    for rid,r in by.items():
        for name,key in [('enqueue','enqueue_ns'),('dispatch','dispatch_ns'),('finish','complete_ns')]:
            events.append((r[key],name,rid))
    events.sort();queue=[];active=set();bypasses=Counter();max_head_bypasses=0
    histogram=Counter();last=events[0][0];decisions=[]
    for now,kind,rid in events:
        histogram[(len(active),bool(queue))]+=(now-last)/1e9;last=now
        if kind=='enqueue':queue.append(rid)
        elif kind=='dispatch':
            assert rid in queue
            head=queue[0]
            if rid!=head:
                bypasses[head]+=1;max_head_bypasses=max(max_head_bypasses,bypasses[head])
            decisions.append(dict(request_id=rid,head_id=head,bypasses_for_head=bypasses[head]))
            queue.remove(rid);active.add(rid)
        else:
            assert rid in active;active.remove(rid)
    assert not queue and not active
    setup=json.loads(Path(f'results/v3/{run_id}.setup.json').read_text())
    cap=setup['runtime']['max_inflight'];policy=setup['gateway_config']
    if 'policy: packing_fifo' in policy or 'policy: residency' in policy:
        assert max_head_bypasses<=setup['runtime'].get('max_bypasses',4),(run_id,max_head_bypasses)
    return dict(run_id=run_id,max_head_bypasses=max_head_bypasses,
        queued_with_spare_slots_s=sum(v for (a,q),v in histogram.items() if q and a<cap),
        queued_with_at_most_one_active_s=sum(v for (a,q),v in histogram.items() if q and a<=1),
        active_request_seconds=sum(a*v for (a,q),v in histogram.items()),
        scope='Ingress intervals; spare ingress slots do not prove GPU idle time',decisions=decisions)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_ids',nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=[audit(r) for r in a.run_ids];a.output.write_text(json.dumps(dict(runs=result),indent=2)+'\n')
    for r in result:print(r['run_id'],r['max_head_bypasses'],round(r['queued_with_at_most_one_active_s'],2))
