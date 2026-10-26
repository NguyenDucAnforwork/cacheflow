"""Opt-in native admission/load diagnostics; no scheduling decisions are changed.

Enabled together with the CUDA transfer diagnostic only. Python timings and these
instrumented runs are excluded from final performance comparisons.
"""
import functools
import hashlib
import json
import os
import time
from pathlib import Path


def emit(row):
    path=Path(os.environ['CACHEFLOW_SGLANG_TRANSFER_LOG']).with_name('sglang_admission_events.jsonl')
    with path.open('a') as file:
        file.write(json.dumps(dict(pid=os.getpid(),monotonic_ns=time.monotonic_ns(),**row),sort_keys=True)+'\n')


def install(module):
    if module.__name__.endswith('schedule_policy'):
        cls=module.PrefillAdder
        original=cls.add_one_req
        @functools.wraps(original)
        def add(self,req,*args,**kwargs):
            if not hasattr(req,'_cacheflow_prefix_group'):
                req._cacheflow_prefix_group=hashlib.sha256(
                    ','.join(map(str,req.origin_input_ids[:1024])).encode()).hexdigest()
                emit(dict(kind='request',rid=req.rid,prefix_group=req._cacheflow_prefix_group,
                    input_tokens=len(req.origin_input_ids),input_ids_sha256=hashlib.sha256(
                        ','.join(map(str,req.origin_input_ids)).encode()).hexdigest()))
            before=dict(gpu_prefix_tokens=len(req.prefix_indices),host_hit_tokens=req.host_hit_length,
                extend_tokens=req.extend_input_len,remaining_total_tokens=self.rem_total_tokens,
                already_selected=len(self.can_run_list))
            result=original(self,req,*args,**kwargs)
            emit(dict(kind='add_one_req',rid=req.rid,prefix_group=req._cacheflow_prefix_group,
                input_tokens=len(req.origin_input_ids),before=before,result=str(result),
                selected=any(r is req for r in self.can_run_list),
                after_gpu_prefix_tokens=len(req.prefix_indices),after_extend_tokens=req.extend_input_len))
            return result
        cls.add_one_req=add
        original_chunk=cls.add_chunked_req
        @functools.wraps(original_chunk)
        def chunk(self,req,*args,**kwargs):
            result=original_chunk(self,req,*args,**kwargs)
            emit(dict(kind='add_chunked_req',rid=req.rid,
                selected=any(r is req for r in self.can_run_list),
                after_gpu_prefix_tokens=len(req.prefix_indices),after_extend_tokens=req.extend_input_len))
            return result
        cls.add_chunked_req=chunk
    elif module.__name__.endswith('hiradix_cache'):
        cls=module.HiRadixCache
        original=cls.load_back
        @functools.wraps(original)
        def load(self,node,mem_quota=None):
            cursor=node;tokens=0
            while cursor.evicted:
                tokens+=len(cursor.host_value);cursor=cursor.parent
            result=original(self,node,mem_quota)
            emit(dict(kind='load_back',requested_host_tokens=tokens,mem_quota=mem_quota,
                threshold=self.load_back_threshold,loaded_tokens=len(result) if result is not None else 0))
            return result
        cls.load_back=load
