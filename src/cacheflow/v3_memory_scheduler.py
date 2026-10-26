"""Residency-aware admission prototype; leaves all engine KV correctness to vLLM."""
from __future__ import annotations

import time

from .prefix import shared_prefix_tokens
from .scheduler import AdmissionScheduler

RESIDENCY_POLICIES={'lpm_real','packing_fifo','residency'}


def tail_reservation(ticket, block_size=16):
    # Reserve the incomplete prompt tail, output budget and one safety block.
    suffix = ticket.input_tokens - len(ticket.engine_blocks)*block_size + ticket.output_budget + block_size
    return ((suffix + block_size - 1)//block_size)*block_size


def reservation_state(tickets, block_size=16):
    blocks=set();tails=0
    for ticket in tickets:
        blocks.update(ticket.engine_blocks)
        tails += tail_reservation(ticket, block_size)
    return blocks,tails


def reserved_tokens(tickets, block_size=16):
    blocks,tails=reservation_state(tickets, block_size)
    return len(blocks)*block_size+tails


def incremental_reservation(active_blocks, active_reserved, ticket, block_size=16):
    return active_reserved + block_size*len(set(ticket.engine_blocks).difference(active_blocks)) + tail_reservation(ticket, block_size)


class ResidencyScheduler(AdmissionScheduler):
    def __init__(self,*,policy,residency_index,kv_capacity_tokens,max_bypasses=4,**kwargs):
        if policy not in RESIDENCY_POLICIES:raise ValueError(policy)
        super().__init__(policy='fifo',**kwargs)
        self.policy=policy;self.residency=residency_index
        self.kv_capacity_tokens=kv_capacity_tokens;self.max_bypasses=max_bypasses
        self._bypasses={}
        self.decision_calls=0;self.decision_cpu_ns=0;self.decision_wall_ns=0;self.decision_max_ns=0
        self.decision_cache_hits=0;self._decision_cache_key=None;self._decision_cache_value=None

    def _eligible(self,ticket,now):return True

    def _cpu_potential(self,ticket):
        return max((shared_prefix_tokens(ticket.engine_blocks,t.engine_blocks,block_size=16)
                    for t in self._recent),default=0)//256*256

    def decision_stats(self):
        return dict(calls=self.decision_calls, cpu_ms=self.decision_cpu_ns/1e6,
                    wall_ms=self.decision_wall_ns/1e6, max_ms=self.decision_max_ns/1e6,
                    cache_hits=self.decision_cache_hits)

    def _choose(self,now):
        start=time.perf_counter_ns()
        start_cpu=time.thread_time_ns()
        try:
            # Prompt/budget fields are immutable. LPM/residency additionally depend
            # on the event sequence; packing only needs the known/unknown gate.
            key=None
            if self.residency.known:
                key=(tuple(t.request_id for t in self._queue),tuple(self._active),
                     tuple(self._bypasses.items()),
                     self.residency.last_sequence if self.policy!='packing_fifo' else None)
                if key==self._decision_cache_key:
                    self.decision_cache_hits+=1
                    return self._decision_cache_value
            result=self._choose_impl(now)
            if key is not None:
                self._decision_cache_key=key;self._decision_cache_value=result
            return result
        finally:
            elapsed=time.perf_counter_ns()-start
            self.decision_calls+=1;self.decision_cpu_ns+=time.thread_time_ns()-start_cpu
            self.decision_wall_ns+=elapsed
            self.decision_max_ns=max(self.decision_max_ns,elapsed)

    def _choose_impl(self,now):
        if len(self._active)>=self.max_inflight or not self._queue:return None
        oldest=self._queue[0]
        oldest.scheduler_head_id=None
        if not self.residency.known:
            oldest.dispatch_reason='unknown_residency_fifo';return oldest
        if self.policy=='lpm_real':
            chosen=max(self._queue,key=lambda t:self.residency.matched_tokens(t.engine_blocks))
            chosen.scheduler_head_id=None;chosen.dispatch_reason='actual_gpu_lpm';return chosen
        active=list(self._active.values())
        if not active:
            oldest.dispatch_reason='oldest_start';return oldest
        if self.policy=='residency':
            gpu={t.request_id:self.residency.matched_tokens(t.engine_blocks) for t in self._queue}
            has_migration=any(self._cpu_potential(t)-gpu[t.request_id]>=1024 for t in self._queue)
            if not has_migration:
                oldest.dispatch_reason='no_migration_fifo';return oldest
        active_blocks,active_tails=reservation_state(active)
        active_reserved=len(active_blocks)*16+active_tails
        fitting=[t for t in self._queue
                 if incremental_reservation(active_blocks,active_reserved,t)<=self.kv_capacity_tokens]
        if oldest in fitting:
            oldest.dispatch_reason='oldest_fits';return oldest
        if self._bypasses.get(oldest.request_id,0)>=self.max_bypasses:
            return None  # drain existing work before this oldest request
        if self.policy=='residency':
            fitting=[t for t in fitting if gpu[t.request_id]>=1024 or any(t.group and t.group==a.group for a in active)]
        if not fitting:return None
        chosen=fitting[0] if self.policy=='packing_fifo' else max(fitting,key=lambda t:gpu[t.request_id])
        chosen.scheduler_head_id=oldest.request_id;chosen.dispatch_reason='compatible_backfill'
        return chosen

    async def admit(self,*args,**kwargs):
        ticket=await super().admit(*args,**kwargs)
        if ticket.scheduler_head_id and ticket.scheduler_head_id!=ticket.request_id:
            head=ticket.scheduler_head_id;self._bypasses[head]=self._bypasses.get(head,0)+1
        else:self._bypasses.pop(ticket.request_id,None)
        ticket.predicted_gpu_tokens=self.residency.matched_tokens(ticket.engine_blocks)
        ticket.reserved_active_tokens=reserved_tokens(self._active.values())
        return ticket
