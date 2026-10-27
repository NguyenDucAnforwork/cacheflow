"""Diagnostic-only native metadata: no extra future/event queries or tensors.

Never enabled for performance comparisons or attached to a running process.
Wrappers preserve original results/exceptions; observation failure is recorded
separately. Snapshots do not prove tensor validity, reachability or root cause.
"""
import functools
import hashlib
import inspect
import json
import os
import sys
import time
from collections import Counter,defaultdict
from pathlib import Path


def emit(kind,payload):
    prefix=os.environ.get('CACHEFLOW_V8_LIVENESS_LOG')
    if not prefix:return
    try:
        path=Path(f'{prefix}.{os.getpid()}.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a') as f:f.write(json.dumps(dict(kind=kind,pid=os.getpid(),monotonic_ns=time.monotonic_ns(),diagnostic_only=True,**payload),sort_keys=True)+'\n')
    except (OSError,TypeError,ValueError):print('V8 diagnostic output unavailable',file=sys.stderr)


def safe_emit(kind,callback):
    try:emit(kind,callback())
    except Exception as exc:emit('probe_error',dict(stage=kind,error=repr(exc)))


def due(obj,name):
    try:
        now=time.monotonic();key='_cacheflow_v8_last_'+name
        if now-getattr(obj,key,-float('inf'))<2:return False
        setattr(obj,key,now);return True
    except Exception as exc:
        emit('probe_error',dict(stage='sampling_gate',error=repr(exc)));return False


def label(value):return value.hex() if isinstance(value,bytes) else hashlib.sha256(repr(value).encode()).hexdigest()


def tracker_record(t):
    if t is None:return None
    return dict(state=getattr(t.state,'name',str(t.state)),vllm_hit_tokens=t.num_vllm_hit_tokens,lmcache_hit_tokens=t.num_lmcache_hit_tokens,
        num_stored_tokens=t.num_stored_tokens,num_scheduled_tokens=t.num_scheduled_tokens,
        allocated_blocks_per_group={str(g):len(b) for g,b in t.allocated_block_ids.items()})


def table_records(manager,rid):
    # Do not call get_blocks(): some versions index a defaultdict and create an
    # empty request table as a side effect. .get() only observes existing tables.
    return [m.req_to_blocks.get(rid,()) for m in manager.coordinator.single_type_managers]


def scheduler_snapshot(scheduler):
    manager=scheduler.kv_cache_manager;pool=manager.block_pool;connector=scheduler.connector
    trackers=getattr(connector,'request_trackers',{});adapter=getattr(connector,'scheduler_adapter',None)
    expected=defaultdict(set);physical=set();requests=[]
    for rid,r in list(scheduler.requests.items()):
        groups=table_records(manager,rid);tables=[]
        for group,blocks in enumerate(groups):
            kept=[b for b in blocks if not getattr(b,'is_null',False)]
            for i,b in enumerate(blocks):
                if getattr(b,'is_null',False):continue
                physical.add(b.block_id)
                if i<len(r.block_hashes):expected[group,label(r.block_hashes[i])].add(b.block_id)
            tables.append(dict(allocated=len(kept),unhashed=sum(b.block_hash is None for b in kept),first_ids=[b.block_id for b in kept[:4]],last_ids=[b.block_id for b in kept[-4:]]))
        requests.append(dict(request_id=rid,status=getattr(r.status,'name',str(r.status)),num_computed_tokens=r.num_computed_tokens,num_tokens=r.num_tokens,
            block_tables=tables,connector_tracker=tracker_record(trackers.get(rid))))
    duplicate=[dict(group=g,expected_hash=h,physical_ids=sorted(ids)) for (g,h),ids in expected.items() if len(ids)>1]
    lookups={}
    if adapter is not None:
        for name in ['_pending_lookups','_finished_lookup_results','_per_server_hits']:
            values=getattr(adapter,name);lookups[name]=dict(count=len(values),first_ids=sorted(values)[:64])
    return dict(requests=requests,status_counts=dict(Counter(r['status'] for r in requests)),running=len(scheduler.running),waiting=len(scheduler.waiting),
        skipped_waiting=len(scheduler.skipped_waiting),free_blocks=pool.get_num_free_blocks(),total_blocks=len(pool.blocks),
        tracked_unique_physical_blocks=len(physical),duplicate_physical_blocks_above_one_per_expected_hash=sum(len(r['physical_ids'])-1 for r in duplicate),duplicate_examples=duplicate[:16],
        global_refcount_histogram=dict(Counter(b.ref_cnt for b in pool.blocks)),finished_recving_kv_req_ids=sorted(scheduler.finished_recving_kv_req_ids),lookup_membership=lookups,
        limitation='Existing metadata only; expected hashes/allocated tables do not prove loaded tensor bytes or completed DMA. Snapshots across processes are not atomic.')


def ready(kind,original):
    path=Path(inspect.unwrap(original).__code__.co_filename)
    safe_emit('hook_ready',lambda:dict(target=kind,method=original.__module__+'.'+original.__qualname__,source_path=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))


def install_scheduler(module):
    cls=module.Scheduler
    if getattr(cls,'_cacheflow_v8_probe',False):return
    original=cls.schedule
    @functools.wraps(original)
    def schedule(self,*a,**kw):
        result=original(self,*a,**kw)
        if due(self,'scheduler'):safe_emit('scheduler',lambda:scheduler_snapshot(self))
        return result
    cls.schedule=schedule;cls._cacheflow_v8_probe=True;ready('scheduler',original)


def install_allocator(module):
    cls=module.KVCacheManager
    if getattr(cls,'_cacheflow_v8_probe',False):return
    original=cls.allocate_slots;signature=inspect.signature(original)
    @functools.wraps(original)
    def allocate(self,*a,**kw):
        result=original(self,*a,**kw)
        if result is None and due(self,'allocation_failure'):
            def snapshot():
                bound=signature.bind(self,*a,**kw);bound.apply_defaults();fields=bound.arguments;r=fields['request']
                return dict(request_id=r.request_id,status=getattr(r.status,'name',str(r.status)),computed_tokens=r.num_computed_tokens,num_tokens=r.num_tokens,
                    arguments={k:fields[k] for k in ['num_new_tokens','num_new_computed_tokens','num_lookahead_tokens','num_external_computed_tokens','delay_cache_blocks','full_sequence_must_fit']},
                    held_blocks_per_group=[len(b) for b in table_records(self,r.request_id)],free_blocks_after=self.block_pool.get_num_free_blocks())
            safe_emit('allocation_failure',snapshot)
        return result
    cls.allocate_slots=allocate;cls._cacheflow_v8_probe=True;ready('allocator',original)


def install_connector(module):
    cls=module.LMCacheMPConnector
    if getattr(cls,'_cacheflow_v8_probe',False):return
    original=cls.build_connector_meta
    @functools.wraps(original)
    def build(self,*a,**kw):
        result=original(self,*a,**kw)
        if due(self,'metadata'):
            def snapshot():
                return dict(operations=[dict(request_id=m.request_id,direction=m.direction,start=m.op.start,end=m.op.end,
                    skip_first_n_tokens=getattr(m.op,'skip_first_n_tokens',0)) for m in result.requests],
                    tracker_states={rid:tracker_record(t) for rid,t in self.request_trackers.items()})
            safe_emit('connector_metadata',snapshot)
        return result
    cls.build_connector_meta=build;cls._cacheflow_v8_probe=True;ready('connector',original)


def install_worker(module):
    cls=module.LMCacheMPWorkerAdapter
    if getattr(cls,'_cacheflow_v8_probe',False):return
    original=cls.get_finished
    @functools.wraps(original)
    def get_finished(self,*a,**kw):
        result=original(self,*a,**kw)
        if due(self,'worker'):
            def snapshot():
                names=['store_futures','retrieve_futures','store_events','retrieve_events','_dropped_retrieves']
                return dict(state={n:dict(count=len(getattr(self,n)),first_ids=sorted(getattr(self,n))[:64]) for n in names},
                    returned_finished_sending=sorted(result[0] or []),returned_finished_recving=sorted(result[1] or []),healthy=self.is_healthy)
            safe_emit('connector_worker',snapshot)
        return result
    cls.get_finished=get_finished;cls._cacheflow_v8_probe=True;ready('worker',original)
