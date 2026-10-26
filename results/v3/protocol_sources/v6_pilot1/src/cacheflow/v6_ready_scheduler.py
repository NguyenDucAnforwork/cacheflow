"""Experimental union admission with at most one unready producer per prefix.

Standalone prototype, not wired into the frozen V5 gateway. First nonempty text
is a conservative frontend readiness signal, not a native allocation/pinning API.
It prevents concurrent pending-prefill followers in the admission model; it does
not prove physical capacity, starvation freedom or upstream transfer liveness.
"""
from __future__ import annotations

import time
from .prefix import shared_prefix_tokens
from .v3_memory_scheduler import ResidencyScheduler,reservation_state,incremental_reservation


class ReadyUnionScheduler(ResidencyScheduler):
    def __init__(self,*,policy='packing_ready',**kwargs):
        if policy!='packing_ready':raise ValueError(policy)
        super().__init__(policy='packing_reuse',**kwargs)
        self.policy=policy;self.readiness_blocked_decisions=0

    def _pending_producer(self,ticket):
        return any(a.first_token_ns is None and shared_prefix_tokens(ticket.engine_blocks,a.engine_blocks,block_size=16)>=self.min_shared_tokens
                   for a in self._active.values())

    def decision_stats(self):
        return super().decision_stats()|dict(readiness_blocked_decisions=self.readiness_blocked_decisions,
            readiness_gate='At most one admitted request without first text per shared prefix; not a physical pin guarantee')

    def _choose(self,now):
        start=time.perf_counter_ns();cpu=time.thread_time_ns()
        try:
            key=(tuple(t.request_id for t in self._queue),
                 tuple((rid,t.first_token_ns is not None) for rid,t in self._active.items()),
                 tuple(self._bypasses.items()),len(self._recent),self._recent[-1].request_id if self._recent else None)
            if key==self._decision_cache_key:
                self.decision_cache_hits+=1;return self._decision_cache_value
            result=self._choose_ready(now)
            self._decision_cache_key=key;self._decision_cache_value=result
            return result
        finally:
            elapsed=time.perf_counter_ns()-start;self.decision_calls+=1
            self.decision_cpu_ns+=time.thread_time_ns()-cpu;self.decision_wall_ns+=elapsed
            self.decision_max_ns=max(self.decision_max_ns,elapsed)

    def _choose_ready(self,now):
        if len(self._active)>=self.max_inflight or not self._queue:return None
        oldest=self._queue[0];oldest.scheduler_head_id=None
        active=list(self._active.values())
        if not active:
            oldest.dispatch_reason='oldest_start';return oldest
        blocks,tails=reservation_state(active);used=len(blocks)*16+tails
        def feasible(ticket):
            if self._pending_producer(ticket):
                self.readiness_blocked_decisions+=1;return False
            return incremental_reservation(blocks,used,ticket)<=self.kv_capacity_tokens
        # Keep the original FIFO fast path for unobserved/no prefix reuse, but
        # never bypass the pending-producer check when an active prefix matches.
        observed={t.group for t in [*self._recent,*active] if t.group is not None}
        if not any(t.group in observed for t in self._queue if t.group is not None):
            if not self._pending_producer(oldest):
                oldest.dispatch_reason='no_observed_prefix_reuse_fifo';return oldest
        if feasible(oldest):
            oldest.dispatch_reason='oldest_ready_fits';return oldest
        if self._bypasses.get(oldest.request_id,0)>=self.max_bypasses:return None
        chosen=next((t for t in self._queue[1:] if feasible(t)),None)
        if chosen:
            chosen.scheduler_head_id=oldest.request_id;chosen.dispatch_reason='ready_compatible_backfill'
        return chosen


class ReadyFifoScheduler(ReadyUnionScheduler):
    """Readiness-only ablation: same gate/backfill bound, no union budget."""
    def __init__(self,*,policy='ready_fifo',**kwargs):
        if policy!='ready_fifo':raise ValueError(policy)
        super().__init__(policy='packing_ready',**kwargs);self.policy=policy

    def _choose_ready(self,now):
        if len(self._active)>=self.max_inflight or not self._queue:return None
        oldest=self._queue[0];oldest.scheduler_head_id=None
        if not self._pending_producer(oldest):
            oldest.dispatch_reason='oldest_ready_fifo';return oldest
        self.readiness_blocked_decisions+=1
        if self._bypasses.get(oldest.request_id,0)>=self.max_bypasses:return None
        chosen=next((t for t in self._queue[1:] if not self._pending_producer(t)),None)
        if chosen:
            chosen.scheduler_head_id=oldest.request_id;chosen.dispatch_reason='ready_fifo_backfill'
        return chosen
