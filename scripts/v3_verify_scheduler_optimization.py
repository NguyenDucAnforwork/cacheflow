"""Check optimized decisions against pinned prototype and time CPU-only choices."""
import argparse
import copy
import json
import random
import statistics
import subprocess
import sys
import time
import types
from pathlib import Path

from cacheflow.scheduler import Ticket
from cacheflow.v3_memory_scheduler import ResidencyScheduler
from cacheflow.v3_residency import ResidencyIndex, engine_block_hashes

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('results/v3/scheduler_optimization_equivalence.json'));args=parser.parse_args()
REFERENCE='d946c93'
source=subprocess.check_output(['git','show',REFERENCE+':src/cacheflow/v3_memory_scheduler.py'],text=True)
module=types.ModuleType('cacheflow._reference_memory_scheduler');sys.modules[module.__name__]=module
exec(compile(source,REFERENCE+':v3_memory_scheduler.py','exec'),module.__dict__)
Legacy=module.ResidencyScheduler
rng=random.Random(191)
lengths=[19504,15206,29172]
blocks=[engine_block_hashes([*range(64),*[g*40000+x+100 for x in range(n-64)]]) for g,n in enumerate(lengths)]


def ticket(name,g):
    return Ticket(request_id=name,blocks=(),arrival_ns=1,enqueued_ns=1,deadline_ns=2,group=str(g),
        engine_blocks=blocks[g],input_tokens=lengths[g],output_budget=96)


def pair(policy,active,queue,recent,index,bypasses):
    result=[]
    for cls in [Legacy,ResidencyScheduler]:
        s=cls(policy=policy,residency_index=copy.deepcopy(index),kv_capacity_tokens=43664,
              max_inflight=16,max_bypasses=4)
        s._active={t.request_id:copy.copy(t) for t in active};s._queue=[copy.copy(t) for t in queue]
        s._recent.extend(copy.copy(t) for t in recent);s._bypasses=copy.copy(bypasses);result.append(s)
    return result


checks=0
for policy in ['packing_fifo','residency','lpm_real']:
    for case in range(30):
        active=[ticket(f'a{i}',rng.randrange(3)) for i in range(rng.randrange(17))]
        queue=[ticket(f'q{i}',rng.randrange(3)) for i in range(rng.randrange(1,25))]
        recent=[ticket(f'r{i}',rng.randrange(3)) for i in range(rng.randrange(12))]
        index=ResidencyIndex();index.known=bool(case%5)
        index.refs.update(blocks[rng.randrange(3)])
        old,new=pair(policy,active,queue,recent,index,{'q0':case%6})
        for _ in range(3):
            a=old._choose(10);b=new._choose(10)
            assert (a.request_id if a else None)==(b.request_id if b else None),(policy,case)
            if a:assert (a.dispatch_reason,a.scheduler_head_id)==(b.dispatch_reason,b.scheduler_head_id)
            checks+=1
index=ResidencyIndex();index.known=True;index.refs.update(blocks[2])
old,new=pair('packing_fifo',[ticket(f'a{i}',2) for i in range(4)],
    [ticket('head',0),*[ticket(f'q{i}',i%3) for i in range(49)]],
    [ticket(f'r{i}',i%3) for i in range(50)],index,{})
results={}
for label,scheduler,clear_cache in [('reference',old,False),('optimized_uncached',new,True),('optimized_repeated',new,False)]:
    times=[]
    for _ in range(40):
        if clear_cache:scheduler._decision_cache_key=None
        start=time.perf_counter_ns();choice=scheduler._choose(10);times.append((time.perf_counter_ns()-start)/1e6)
    results[label]=dict(median_ms=statistics.median(times),max_ms=max(times),selected=choice.request_id if choice else None)
assert len({x['selected'] for x in results.values()})==1
path=args.output;assert not path.exists()
path.write_text(json.dumps(dict(reference_commit=REFERENCE,checks=checks,matched_decisions=True,
    scope='CPU-only microbenchmark; synthetic block contents at trace-derived sizes; no profiler enabled; not E2E latency',
    timings=results),indent=2)+'\n')
print('Matched',checks,'decisions');print(json.dumps(results,indent=2))
