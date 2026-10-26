"""Optional same-batch delay-hit guard, inspired by Strata section4.3.1.

This is a component adaptation, NOT a full Strata implementation. It prevents a
follower from recomputing >100 matching tokens being prefilled by a request already
selected in this batch. Native KV lookup, allocation, loading and execution remain
unchanged. Deferred requests stay in the native waiting queue for the next round.
It does not model all inter-batch/in-flight transient nodes or balanced/bubble work.
"""
import functools


def duplicate_producer(req,selected,threshold=100):
    """Find a selected request computing an uncached matching prefix interval.

    Compare exact CPU token arrays, including the whole preceding prefix. No GPU
    reads or synchronization. Host hits count as cached, so a restore-only bundle
    is not incorrectly treated as duplicated compute.
    """
    # This adaptation targets MHA. Hybrid allocators have request-side resources
    # that the native break/cleanup path owns; do not defer them here.
    if getattr(req,'mamba_pool_idx',None) is not None:return None
    tokens=getattr(req,'full_untruncated_fill_ids',req.origin_input_ids)
    cached=len(req.prefix_indices)+req.host_hit_length
    for producer in selected:
        if producer is req:continue
        if getattr(req,'extra_key',None)!=getattr(producer,'extra_key',None):continue
        start=max(cached,len(producer.prefix_indices))
        end=min(len(producer.prefix_indices)+producer.extend_input_len,len(tokens))
        check=start+threshold+1
        if check>end:continue
        other=getattr(producer,'full_untruncated_fill_ids',producer.origin_input_ids)
        if check<=len(other) and tokens[:check]==other[:check]:
            return producer
    return None


def install(module):
    cls=module.PrefillAdder
    if getattr(cls,'_cacheflow_same_batch_guard',False):return
    original=cls.add_one_req
    @functools.wraps(original)
    def guarded(self,req,*args,**kwargs):
        producer=duplicate_producer(req,self.can_run_list)
        if producer is not None:
            # The scheduler retains requests absent from can_run_list. CONTINUE
            # permits complementary work to fill the rest of this batch.
            return module.AddReqResult.CONTINUE
        return original(self,req,*args,**kwargs)
    cls.add_one_req=guarded
    cls._cacheflow_same_batch_guard=True
