"""Outside-window construction/process identity for a future V7 GPU study."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import httpx
import psutil
from v4_services import service_pid

ROOT=Path(__file__).resolve().parents[1]
SOURCES=['src/cacheflow/'+p for p in ['v7_gateway.py','v7_epoch_scheduler.py','v6_ready_scheduler.py','v3_memory_scheduler.py','scheduler.py','gateway.py']]
CLASSES={'reference':{'fifo':'cacheflow.scheduler.AdmissionScheduler','bundle_wave':'cacheflow.v3_scheduler.BaselineScheduler',
    'packing_reuse':'cacheflow.v3_memory_scheduler.ResidencyScheduler','packing_ready':'cacheflow.v6_ready_scheduler.ReadyUnionScheduler','ready_fifo':'cacheflow.v6_ready_scheduler.ReadyFifoScheduler'},
    'epoch':{'packing_reuse':'cacheflow.v7_epoch_scheduler.EpochUnionScheduler','packing_ready':'cacheflow.v7_epoch_scheduler.EpochReadyUnionScheduler','ready_fifo':'cacheflow.v7_epoch_scheduler.EpochReadyFifoScheduler'}}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_identity(record,policy,implementation):
    assert implementation in CLASSES and policy in CLASSES[implementation]
    assert record['implementation']==implementation and record['policy']==policy
    assert record['scheduler_class']==CLASSES[implementation][policy],'Unexpected runtime scheduler class'
    expected={str((ROOT/name).resolve()):sha(ROOT/name) for name in SOURCES}
    assert record['source_sha256']==expected,'Startup source identity differs from current registered files'
    if implementation=='epoch':
        expected_selector={'packing_reuse':'cacheflow.v3_memory_scheduler.ResidencyScheduler._choose_impl',
            'packing_ready':'cacheflow.v6_ready_scheduler.ReadyUnionScheduler._choose_ready','ready_fifo':'cacheflow.v6_ready_scheduler.ReadyFifoScheduler._choose_ready'}[policy]
    else:expected_selector=CLASSES[implementation][policy]+'._choose'
    assert record['selector']==expected_selector,'Changed selection function identity'


def capture(url,policy,implementation,*,require_fresh=False):
    pid=service_pid('cacheflow_v2_gateway');assert pid>0
    process=psutil.Process(pid);argv=process.cmdline();birth=process.create_time()
    assert 'cacheflow.v7_gateway:create_app' in argv,'Wrong gateway factory'
    assert process.environ().get('CACHEFLOW_SCHEDULER_IMPLEMENTATION')==implementation
    start=time.monotonic_ns()
    with httpx.Client(timeout=10) as client:
        response=client.get(url.rstrip('/')+'/implementation');response.raise_for_status();record=response.json()
        response=client.get(url.rstrip('/')+'/health');response.raise_for_status();health=response.json()
    end=time.monotonic_ns();validate_identity(record,policy,implementation)
    assert health['policy']==policy and health['queue']==health['active']==0,'Boundary gateway must be idle'
    if implementation=='epoch':assert health['decision_stats']['cache_key_kind']=='lifecycle_epoch_prototype'
    if require_fresh:
        assert health['completed_history_requests']==0
        if health['decision_stats'] is not None:assert health['decision_stats']['calls']==health['decision_stats']['cache_hits']==0
    assert service_pid('cacheflow_v2_gateway')==pid and psutil.Process(pid).create_time()==birth
    return dict(gateway_pid=pid,gateway_create_time=birth,gateway_argv=argv,implementation_record=record,health=health,
        start_ns=start,end_ns=end,observer_source_sha256=sha(__file__),
        scope='Outside-window factory/process/startup-source identity; no completed replay, performance, quality or source-equivalence claim.')


def validate_pair(before,after):
    for key in ['gateway_pid','gateway_create_time','gateway_argv','implementation_record','observer_source_sha256']:assert before[key]==after[key],key
    assert before['gateway_pid']>0 and 'cacheflow.v7_gateway:create_app' in before['gateway_argv']
    assert before['observer_source_sha256']==sha(__file__)
    assert before['end_ns']<after['start_ns']
    for row in [before,after]:
        record=row['implementation_record'];validate_identity(record,record['policy'],record['implementation'])
        assert row['health']['policy']==record['policy']
        assert row['health']['active']==row['health']['queue']==0
        if record['implementation']=='epoch':assert row['health']['decision_stats']['cache_key_kind']=='lifecycle_epoch_prototype'
    assert before['health']['completed_history_requests']==0
    if before['health']['decision_stats'] is not None:assert before['health']['decision_stats']['calls']==before['health']['decision_stats']['cache_hits']==0


def validate_replay_window(before,after,requests):
    validate_pair(before,after)
    assert requests,'Identity boundaries need a nonempty request ledger'
    assert before['end_ns']<min(r['scheduled_arrival_ns'] for r in requests),'Initial identity capture overlaps request window'
    assert after['start_ns']>max(r['complete_ns'] for r in requests),'Final identity capture precedes response completion'


def write(path,value):
    with Path(path).open('x') as out:out.write(json.dumps(value,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('capture');c.add_argument('url');c.add_argument('policy');c.add_argument('implementation',choices=list(CLASSES));c.add_argument('--fresh',action='store_true');c.add_argument('--output',type=Path,required=True)
    c=sub.add_parser('verify-pair');c.add_argument('before',type=Path);c.add_argument('after',type=Path);c.add_argument('--requests',type=Path,required=True);c.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.command=='capture':write(a.output,capture(a.url,a.policy,a.implementation,require_fresh=a.fresh))
    else:
        before=json.loads(a.before.read_text());after=json.loads(a.after.read_text());requests=[json.loads(line) for line in a.requests.read_text().splitlines()];validate_replay_window(before,after,requests)
        write(a.output,dict(complete_identity_pair=True,before_sha256=sha(a.before),after_sha256=sha(a.after),
            request_file_sha256=sha(a.requests),requests=len(requests),observer_source_sha256=sha(__file__),scope='Gateway identity boundaries bracket the request ledger, not a complete GPU configuration/request/quality audit.'))
