"""CPU-only decision microprofile at trace-derived sizes; not an E2E latency result."""
import argparse
import cProfile
import io
import json
import pstats
import statistics
import time
from pathlib import Path

from cacheflow.scheduler import Ticket
from cacheflow.v3_memory_scheduler import ResidencyScheduler
from cacheflow.v3_residency import ResidencyIndex, engine_block_hashes


def main():
    p=argparse.ArgumentParser();p.add_argument('--label',required=True);p.add_argument('--repeat',type=int,default=3);a=p.parse_args()
    rows=[json.loads(l) for l in Path('data/processed/v3/dev4b3-qps2-s101.jsonl').read_text().splitlines()]
    lengths={r['sample_id']:r['input_tokens'] for r in rows}
    groups={k:engine_block_hashes([i+g*40000 for i in range(n)]) for g,(k,n) in enumerate(lengths.items())}
    def ticket(name,group):
        return Ticket(request_id=name,blocks=(),arrival_ns=1,enqueued_ns=1,deadline_ns=2,group=group,
            engine_blocks=groups[group],input_tokens=lengths[group],output_budget=96)
    group_names=list(groups);active_group=max(group_names,key=lambda k:lengths[k])
    first_group=next(g for g in group_names if g!=active_group)
    index=ResidencyIndex();index.known=True;index.refs.update(groups[active_group])
    scheduler=ResidencyScheduler(policy='packing_fifo',residency_index=index,
        kv_capacity_tokens=43664,max_inflight=16)
    scheduler._active={f'active{i}':ticket(f'active{i}',active_group) for i in range(4)}
    order=[first_group,*[group_names[i%len(group_names)] for i in range(49)]]
    scheduler._queue=[ticket(f'queue{i}',g) for i,g in enumerate(order)]
    scheduler._recent.extend(ticket(f'recent{i}',group_names[i%len(group_names)]) for i in range(50))
    timings=[];prof=cProfile.Profile();selected=[]
    for _ in range(a.repeat):
        start=time.perf_counter_ns();prof.enable();choice=scheduler._choose(time.monotonic_ns());prof.disable()
        timings.append((time.perf_counter_ns()-start)/1e6);selected.append(choice.request_id if choice else None)
    out=Path(f'results/v3/scheduler_cpu_{a.label}.json')
    assert not out.exists(),'refuse overwrite'
    stream=io.StringIO();pstats.Stats(prof,stream=stream).strip_dirs().sort_stats('cumtime').print_stats(12)
    result=dict(scope='CPU-only diagnostic, synthetic block contents with trace-derived lengths; cProfile adds overhead; not E2E',
        label=a.label,active=4,queued=50,recent=50,input_tokens_by_group=lengths,
        repeat=a.repeat,decision_ms=timings,median_ms=statistics.median(timings),selected=selected,
        profile=stream.getvalue())
    out.write_text(json.dumps(result,indent=2)+'\n');print(result['median_ms']);print(stream.getvalue())


if __name__=='__main__':main()
