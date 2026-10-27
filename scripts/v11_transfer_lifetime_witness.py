"""Conditional native cancellation/completion witness, no serving activation.

Runs complete selected installed method bodies on CPU metadata fixtures. Future
readiness, terminal signal order and block ownership are assumed test inputs;
there are no actual IPC/CUDA operations, tensor contents or recorded request IDs.
"""
import argparse
import ast
import copy
import enum
import json
import traceback
from pathlib import Path
from types import MethodType,SimpleNamespace as NS
from v6_raw_archive import sha
from v8_allocation_witness import extract

SCHED=Path('/venv/main/lib/python3.12/site-packages/vllm/v1/core/sched/scheduler.py')
ADAPTER=Path('/venv/main/lib/python3.12/site-packages/lmcache/integration/vllm/vllm_multi_process_adapter.py')
CONNECTOR=ADAPTER.with_name('lmcache_mp_connector.py')
REQUEST=SCHED.parents[2]/'request.py'


def statuses():
    node=copy.deepcopy(next(n for n in ast.parse(REQUEST.read_text()).body if isinstance(n,ast.ClassDef) and n.name=='RequestStatus'))
    module=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),node],type_ignores=[])
    scope=dict(enum=enum);exec(compile(ast.fix_missing_locations(module),str(REQUEST),'exec'),scope)
    return scope['RequestStatus']


class Queue:
    def __init__(self,values=()):self.values=list(values)
    def remove_requests(self,requests):self.values=[r for r in self.values if r not in requests]


class Future:
    def __init__(self,ready=False):self.ready=ready;self.queries=0;self.results=0
    def query(self):self.queries+=1;return self.ready
    def result(self,timeout):
        assert self.ready and timeout==60
        self.results+=1;return True


def state(*,with_store=False):
    proofs=[];events=[];Status=statuses();rid='cpu-cancelled-fixture'
    def method(path,owner,name,namespace=None):
        fn,proof=extract(path,owner,name,namespace);proofs.append(proof);return fn
    recv=Future();store=Future() if with_store else None
    worker=NS(dispatcher=None,is_healthy=True,store_futures={rid:store} if store else {},retrieve_futures={rid:(recv,[1,2])},
        store_events={},retrieve_events={},_dropped_retrieves=set(),error_block_ids=set(),finished_stores=set(),previously_finished=set(),_returned_finished=set(),
        request_telemetry=NS(on_request_store_finished=lambda **kwargs:None),model_name='cpu-fixture',world_size=1,worker_id=0)
    for name in ['get_finished','_process_finished_stores','_update_and_get_finished_store']:
        setattr(worker,name,MethodType(method(ADAPTER,'LMCacheMPWorkerAdapter',name,dict(logger=NS(error=lambda *args,**kwargs:None))),worker))
    connector=NS(_cleanup_request_tracker=lambda request_id:events.append('connector_tracker_cleanup'),
        scheduler_adapter=NS(end_session=lambda request_id:events.append('connector_end_session')),
        update_connector_output=lambda output:None)
    connector.request_finished=MethodType(method(CONNECTOR,'LMCacheMPConnector','request_finished'),connector)
    req=NS(request_id=rid,status=Status.WAITING_FOR_REMOTE_KVS,client_index=0,kv_transfer_params=None,num_computed_tokens=0)
    req.is_finished=lambda:Status.is_finished(req.status)
    freed=[]
    def free(request):
        freed.append(dict(request_id=request.request_id,receive_pending=not recv.ready,store_pending=store is not None and not store.ready))
    scheduler=NS(requests={rid:req},running=[],waiting=Queue([req]),skipped_waiting=Queue(),
        num_waiting_for_streaming_input=0,finished_recving_kv_req_ids=set(),failed_recving_kv_req_ids=set(),
        connector=connector,finished_req_ids=set(),finished_req_ids_dict=None,
        encoder_cache_manager=NS(free=lambda request:None),
        kv_cache_manager=NS(free=free,remove_skipped_blocks=lambda **kwargs:None,get_block_ids=lambda request_id:([1,2],)),
        kv_cache_config=NS(kv_cache_groups=[None]))
    globals_=dict(RequestStatus=Status,SupportsHMA=type('UnusedHMA',(),{}),logger=NS(debug=lambda *args,**kwargs:None))
    for name in ['finish_requests','_free_request','_free_blocks','_connector_finished','_update_from_kv_xfer_finished']:
        setattr(scheduler,name,MethodType(method(SCHED,'Scheduler',name,globals_),scheduler))
    return NS(worker=worker,scheduler=scheduler,request=req,recv=recv,store=store,freed=freed,events=events,proofs=proofs,Status=Status,rid=rid)


def scenario(order,*,repeat_terminal=False):
    fixture=state(with_store=order!='receive_late_no_store')
    s,w=fixture.scheduler,fixture.worker;rid=fixture.rid
    assert s.finish_requests(rid,fixture.Status.FINISHED_ABORTED)==[(rid,0)]
    assert rid in s.requests and not fixture.freed,'Native scheduler initially retains blocks for the cancelled async request'
    # All operations already registered in worker before cancellation. No later
    # submissions, ID reuse or cross-thread mutation is part of this fixture.
    if order=='receive_late_no_store':steps=[(False,None),(True,None)]
    elif order=='store_first':steps=[(False,True),(True,True)]
    elif order=='receive_first':steps=[(True,False),(True,True)]
    elif order=='simultaneous':steps=[(True,True)]
    else:raise ValueError(order)
    rounds=[];error=None
    for i,(r_ready,s_ready) in enumerate(steps):
        fixture.recv.ready=r_ready
        if fixture.store is not None:fixture.store.ready=s_ready
        stores,receives=w.get_finished({rid} if i==0 or repeat_terminal else set())
        row=dict(round=i,receive_ready=r_ready,store_ready=s_ready,finished_sending=sorted(stores or ()),finished_recving=sorted(receives or ()))
        try:s._update_from_kv_xfer_finished(NS(finished_sending=stores,finished_recving=receives))
        except AssertionError:
            tb=traceback.extract_tb(__import__('sys').exc_info()[2]);site=tb[-1]
            error=dict(type='AssertionError',path=site.filename,line=site.lineno,method=site.name);row['assertion']=error
        row['request_retained']=rid in s.requests;row['frees']=copy.deepcopy(fixture.freed);rounds.append(row)
        if error:break
    assert error is not None
    return dict(order=order,repeat_terminal_signal=repeat_terminal,rounds=rounds,assertion=error,
        freed_while_operation_pending=any(r['receive_pending'] or r['store_pending'] for r in fixture.freed),
        future_queries=dict(receive=fixture.recv.queries,store=fixture.store.queries if fixture.store else None),native_method_bodies=fixture.proofs)


def positive_control():
    fixture=state();fixture.recv.ready=True;s,w=fixture.scheduler,fixture.worker;rid=fixture.rid
    stores,receives=w.get_finished(set());s._update_from_kv_xfer_finished(NS(finished_sending=stores,finished_recving=receives))
    assert rid in s.requests and rid in s.finished_recving_kv_req_ids and not fixture.freed
    s.finish_requests(rid,fixture.Status.FINISHED_ABORTED)
    stores,receives=w.get_finished({rid});s._update_from_kv_xfer_finished(NS(finished_sending=stores,finished_recving=receives))
    assert rid not in s.requests and fixture.freed==[dict(request_id=rid,receive_pending=False,store_pending=False)]
    return dict(normal_receive_then_cancel=True,exactly_one_safe_free=True,no_assertion=True)


def run():
    cases=[scenario(order,repeat_terminal=repeat) for order in ['receive_late_no_store','store_first','receive_first','simultaneous'] for repeat in [False,True]]
    observed=Path('results/v3/v9repair2_idempotent901_failure_postmortem.json');actual=json.loads(observed.read_text())
    matched=[r['order'] for r in cases if r['assertion']['line']==actual['native_fatal_site']['line']]
    assert set(matched)=={'receive_late_no_store','store_first'}
    return dict(kind='conditional_native_transfer_lifetime_cpu_witness',cpu_only=True,synthetic_metadata=True,gpu_execution=False,
        installed_files_modified=False,live_failure_reproduced=False,source_sha256=sha(__file__),
        native_source_sha256={str(p):sha(p) for p in [SCHED,ADAPTER,CONNECTOR,REQUEST]},
        linked_observed_failure_sha256=sha(observed),cases=cases,positive_control=positive_control(),
        scope='Selected complete installed scheduler/connector/worker method bodies, with decorators omitted and deferred annotations. CPU futures/queues/block-free callbacks and cancellation/completion ordering are fixtures. Eight cases expose completion ownership hazards; two order families reach the same receive-loop assertion line as the actual full failure. Missing native request ID/order/pending-future state is not recovered, so this is not actual root-cause or earlier-stall reproduction. No CUDA/IPC/tensor/fairness/quality/performance proof, native source edit or serving activation.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();value=run()
    with a.output.open('x') as out:out.write(json.dumps(value,indent=2)+'\n')
    print('Eight conditional native completion cases and one positive control executed on CPU; no live reproduction',flush=True)
