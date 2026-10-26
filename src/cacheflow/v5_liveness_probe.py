"""Opt-in diagnostic snapshots of native scheduler blocks and connector futures.

Never enable in a latency comparison. It changes no admission/cache/connector
result and never queries/synchronizes CUDA events or reads prompt/output text.
"""
import functools
import hashlib
import json
import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


def _hash_label(value):
    if isinstance(value,bytes):return value.hex()
    return hashlib.sha256(repr(value).encode()).hexdigest()


def scheduler_snapshot(scheduler):
    manager=scheduler.kv_cache_manager;pool=manager.block_pool
    requests=[];expected=defaultdict(set);physical=set()
    for rid,request in list(scheduler.requests.items()):
        groups=manager.get_blocks(rid).blocks
        hashes=request.block_hashes
        tables=[]
        for group_id,blocks in enumerate(groups):
            table=[]
            for index,block in enumerate(blocks):
                if getattr(block,'is_null',False):continue
                physical.add(block.block_id)
                table.append(dict(block_id=block.block_id,ref_cnt=block.ref_cnt,hashed=block.block_hash is not None))
                if index<len(hashes):expected[(group_id,_hash_label(hashes[index]))].add(block.block_id)
            tables.append(dict(blocks=len(table),unhashed=sum(not b['hashed'] for b in table),
                first_blocks=table[:4],last_blocks=table[-4:]))
        requests.append(dict(request_id=rid,status=getattr(request.status,'name',str(request.status)),num_computed_tokens=request.num_computed_tokens,
            num_tokens=request.num_tokens,block_tables=tables))
    duplicate=[dict(group_id=g,expected_prefix_hash=h,physical_block_ids=sorted(ids)) for (g,h),ids in expected.items() if len(ids)>1]
    all_blocks=pool.blocks
    return dict(requests=requests,status_counts=dict(Counter(r['status'] for r in requests)),
        running=len(scheduler.running),waiting=len(scheduler.waiting),skipped_waiting=len(scheduler.skipped_waiting),
        free_blocks=pool.get_num_free_blocks(),total_blocks=len(all_blocks),
        global_refcount_histogram=dict(Counter(b.ref_cnt for b in all_blocks)),
        tracked_request_unique_physical_blocks=len(physical),
        duplicated_expected_prefix_hashes=len(duplicate),
        duplicate_physical_blocks_above_one_per_expected_hash=sum(len(d['physical_block_ids'])-1 for d in duplicate),
        duplicate_examples=duplicate[:16],
        finished_recving_kv_req_ids=sorted(scheduler.finished_recving_kv_req_ids),
        limitation='Expected hashes identify duplicated logical prefix identities in allocated tables; unhashed/pending blocks do not prove successful transfers or valid tensor content. Full-attention single-group interpretation is used here.')


def worker_snapshot(adapter,result):
    names=['store_futures','retrieve_futures','previously_finished','finished_stores','_returned_finished','store_events','retrieve_events']
    return dict(state={name:dict(count=len(getattr(adapter,name,{})),first_ids=sorted(getattr(adapter,name,{}))[:64]) for name in names},
        returned_finished_sending=sorted(result[0] or []),returned_finished_recving=sorted(result[1] or []),
        healthy=adapter.is_healthy,
        limitation='Membership only; no extra future/event queries, synchronization, retries or state mutation.')


def _emit(kind,payload):
    prefix=os.environ.get('CACHEFLOW_VLLM_LIVENESS_LOG')
    if not prefix:return
    try:
        path=Path(f'{prefix}.{os.getpid()}.jsonl');path.parent.mkdir(parents=True,exist_ok=True)
        row=dict(kind=kind,pid=os.getpid(),monotonic_ns=time.monotonic_ns(),diagnostic_only=True,**payload)
        with path.open('a') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
    except (OSError,TypeError,ValueError):
        # Diagnostic output failure must never change native serving behavior.
        # Missing snapshots make the diagnostic incomplete, not successful.
        print('CacheFlow diagnostic snapshot unavailable',file=sys.stderr)


def install_scheduler(module):
    cls=module.Scheduler
    if getattr(cls,'_cacheflow_liveness_probe',False):return
    original=cls.schedule
    @functools.wraps(original)
    def schedule(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        now=time.monotonic()
        if now-getattr(self,'_cacheflow_probe_last',0)>=2:
            self._cacheflow_probe_last=now
            try:_emit('scheduler',scheduler_snapshot(self))
            except Exception as exc:_emit('probe_error',dict(stage='scheduler',error=repr(exc)))
        return result
    cls.schedule=schedule;cls._cacheflow_liveness_probe=True


def install_worker(module):
    cls=module.LMCacheMPWorkerAdapter
    if getattr(cls,'_cacheflow_liveness_probe',False):return
    original=cls.get_finished
    @functools.wraps(original)
    def get_finished(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        now=time.monotonic()
        if now-getattr(self,'_cacheflow_probe_last',0)>=2:
            self._cacheflow_probe_last=now
            try:_emit('connector_worker',worker_snapshot(self,result))
            except Exception as exc:_emit('probe_error',dict(stage='worker',error=repr(exc)))
        return result
    cls.get_finished=get_finished;cls._cacheflow_liveness_probe=True
