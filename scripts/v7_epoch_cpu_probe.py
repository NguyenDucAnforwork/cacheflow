"""Queued synthetic CPU probe; never benchmarks while serving is active."""
import argparse
import json
import os
import platform
import random
import statistics
import time
from datetime import datetime,timezone
from pathlib import Path
import psutil
from cacheflow.scheduler import Ticket
from cacheflow.v3_memory_scheduler import ResidencyScheduler
from cacheflow.v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler
from cacheflow.v3_residency import ResidencyIndex,engine_block_hashes
from cacheflow.v7_epoch_scheduler import EpochUnionScheduler,EpochReadyUnionScheduler,EpochReadyFifoScheduler
from v6_raw_archive import sha
from v6_regenerate_full_inputs import wait_parent,idle

PARENT=Path('results/v3/v6full1_r1_namespace_preparation_registration.json')
CLASSES={'packing_reuse':(ResidencyScheduler,EpochUnionScheduler),'packing_ready':(ReadyUnionScheduler,EpochReadyUnionScheduler),'ready_fifo':(ReadyFifoScheduler,EpochReadyFifoScheduler)}
NOW=1000000000
PREFIX=engine_block_hashes(list(range(1024)))
BLOCKS=tuple(b.hex() for b in PREFIX)


def make_ticket(rid,first=None):
    return Ticket(request_id=rid,blocks=BLOCKS,arrival_ns=0,enqueued_ns=0,deadline_ns=0,group='probe-prefix',
        first_token_ns=first,engine_blocks=PREFIX,input_tokens=1024,output_budget=96)


def make_state(cls,policy,queue):
    s=cls(policy=policy,residency_index=ResidencyIndex(),kv_capacity_tokens=1500,max_inflight=64,max_queue=512,
        block_size=16,min_shared_tokens=1024,max_bypasses=8)
    for i in range(4):s._active[f'active-{i}']=make_ticket(f'active-{i}',1 if i<3 else None)
    s._queue.extend(make_ticket(f'queued-{i}') for i in range(queue));s._bypasses['queued-0']=8
    # Four shared-prefix requests reserve1024+4*112=1472tokens. A follower
    # cannot fit1500; readiness variants also see the one unready producer.
    assert s._choose(NOW) is None and s._next_timeout(None,NOW)==.1
    return s


def smoke(output):
    output=Path(output);assert not output.exists();cases=[]
    for policy,classes in CLASSES.items():
        for queue in [16,64,128,256,512]:
            for cls in classes:
                s=make_state(cls,policy,queue)
                assert all(s._choose(NOW) is None and s._next_timeout(None,NOW)==.1 for _ in range(3))
            cases.append(dict(policy=policy,queue=queue,legacy_and_prototype_blocked=True))
    with output.open('x') as out:out.write(json.dumps(dict(complete_timing_probe=False,synthetic_state_smoke=True,source_sha256=sha(__file__),
        prototype_sha256=sha('src/cacheflow/v7_epoch_scheduler.py'),cases=cases,
        scope='Untimed tiny fixture checks only; no CPU speedup, real1986QA replay, GPU activation or serving result.'),indent=2)+'\n')


def register(pid,path,smoke_path):
    path=Path(path);assert not path.exists();process=psutil.Process(pid);argv=process.cmdline()
    assert process.is_running() and process.status()!=psutil.STATUS_ZOMBIE
    assert argv[-3:]==['scripts/v6_after_input_reproduction.py','execute',str(PARENT)]
    proof=json.loads(Path(smoke_path).read_text());assert proof['source_sha256']==sha(__file__) and proof['synthetic_state_smoke'] is True
    assert proof['prototype_sha256']==sha('src/cacheflow/v7_epoch_scheduler.py') and len(proof['cases'])==15
    sources=[__file__,'src/cacheflow/v7_epoch_scheduler.py','src/cacheflow/scheduler.py','src/cacheflow/v3_memory_scheduler.py',
        'src/cacheflow/v6_ready_scheduler.py','src/cacheflow/v3_residency.py','scripts/v6_regenerate_full_inputs.py','scripts/v6_raw_archive.py']
    r=dict(kind='synthetic_epoch_cpu_probe_after_all_queued_work',registered_utc=datetime.now(timezone.utc).isoformat(),after_pid=pid,after_create_time=process.create_time(),after_argv=argv,
        parent_registration_sha256=sha(PARENT),smoke_path=str(smoke_path),smoke_sha256=sha(smoke_path),source_sha256={str(p):sha(p) for p in sources},
        policies=list(CLASSES),queues=[16,64,128,256,512],kernels=['chooser_hit','timeout_hit','poll_mutating'],iterations=2000,rounds=5,case_order_seed=919,
        fixture=dict(active=4,ready_active=3,prefix_tokens=1024,output_budget=96,kv_capacity_tokens=1500,cap=64,max_queue=512,max_bypasses=8,all_deadlines_expired=True),
        scope='Synthetic valid blocked states; all45cases retained, paired alternating order, no performance threshold/selection. Wait for namespace-preparation process to end successfully and services idle before CPU timing. No new inference, model weights, prompt tokenizer, GPU profiling or E2E speedup claim.')
    with path.open('x') as out:out.write(json.dumps(r,indent=2)+'\n')


def timed(s,kernel,iterations):
    replacements=[make_ticket(f'replacement-{i}') for i in range((iterations+127)//128)]
    start_wall=time.perf_counter_ns();start_cpu=time.thread_time_ns()
    for i in range(iterations):
        if kernel=='chooser_hit':assert s._choose(NOW) is None
        elif kernel=='timeout_hit':assert s._next_timeout(None,NOW)==.1
        else:
            if i%128==0:s._queue.pop();s._queue.append(replacements[i//128])
            assert s._choose(NOW) is None and s._next_timeout(None,NOW)==.1
    cpu=time.thread_time_ns()-start_cpu;wall=time.perf_counter_ns()-start_wall
    return dict(thread_cpu_ns_per_iteration=cpu/iterations,wall_ns_per_iteration=wall/iterations,
        decision_stats=s.decision_stats())


def execute(path):
    path=Path(path);r=json.loads(path.read_text());output=path.with_suffix('.result.json')
    assert r['kind']=='synthetic_epoch_cpu_probe_after_all_queued_work'
    assert not output.exists() and not path.with_suffix('.failure.json').exists()
    print('Waiting for namespace-preparation parent',r['after_pid'],flush=True);wait_parent(r);idle()
    assert sha(PARENT)==r['parent_registration_sha256'] and sha(r['smoke_path'])==r['smoke_sha256']
    parent_result=PARENT.with_suffix('.result.json');parent=json.loads(parent_result.read_text())
    assert parent['complete_namespace_preparation'] is True and parent['gpu_execution'] is False
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    cases=[dict(policy=p,queue=q,kernel=k) for p in r['policies'] for q in r['queues'] for k in r['kernels']]
    random.Random(r['case_order_seed']).shuffle(cases);results=[]
    environment=dict(python=platform.python_version(),pythonhashseed=os.environ.get('PYTHONHASHSEED'),cpu_count=os.cpu_count(),affinity=psutil.Process().cpu_affinity(),loadavg=os.getloadavg())
    for case in cases:
        idle();pair=CLASSES[case['policy']];samples={'legacy':[],'prototype':[]}
        for round_id in range(r['rounds']):
            order=[0,1] if round_id%2==0 else [1,0]
            for which in order:
                state=make_state(pair[which],case['policy'],case['queue'])
                samples[['legacy','prototype'][which]].append(timed(state,case['kernel'],r['iterations'])|dict(round=round_id,order=order.index(which)))
        medians={name:statistics.median(s['thread_cpu_ns_per_iteration'] for s in values) for name,values in samples.items()}
        results.append(case|dict(samples=samples,median_thread_cpu_ns_per_iteration=medians,legacy_over_prototype_cpu_ratio=medians['legacy']/medians['prototype']))
        print('CPU probe case',case,flush=True)
    with output.open('x') as out:out.write(json.dumps(dict(complete=True,synthetic=True,gpu_execution=False,registration_sha256=sha(path),parent_result_sha256=sha(parent_result),environment=environment,cases=results,
        scope='Synthetic blocked-state CPU timings only, including probe loop/assertions and version-update overhead in mutating polls. Fixed1024-token prefixes are not full-model snapshots. No CI, real-request trace timing, native DMA measurement, gateway total CPU, latency saved or full1986QA/GPU improvement inferred.'),indent=2)+'\n')
    print('Synthetic CPU probe complete; no GPU or E2E result',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('smoke');a.add_argument('output',type=Path)
    a=sub.add_parser('register');a.add_argument('pid',type=int);a.add_argument('output',type=Path);a.add_argument('--smoke',type=Path,required=True)
    a=sub.add_parser('execute');a.add_argument('registration',type=Path);a=p.parse_args()
    if a.command=='smoke':smoke(a.output)
    elif a.command=='register':register(a.pid,a.output,a.smoke);print('Registered CPU-only prototype probe',a.output,flush=True)
    else:
        try:execute(a.registration)
        except Exception as exc:
            with a.registration.with_suffix('.failure.json').open('x') as out:out.write(json.dumps(dict(complete=False,error=repr(exc),scope='Preserved CPU-probe failure; no serving changes or automatic retry'),indent=2)+'\n')
            raise
