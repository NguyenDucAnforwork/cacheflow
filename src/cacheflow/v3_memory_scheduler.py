"""Residency-aware admission prototype; leaves all engine KV correctness to vLLM."""
from __future__ import annotations

from .prefix import shared_prefix_tokens
from .scheduler import AdmissionScheduler

RESIDENCY_POLICIES={'lpm_real','packing_fifo','residency'}


def reserved_tokens(tickets,block_size=16):
    blocks=set();tails=0
    for t in tickets:
        blocks.update(t.engine_blocks)
        # One extra block covers logits-tail recompute/copy-on-write ambiguity.
        suffix=t.input_tokens-len(t.engine_blocks)*block_size+t.output_budget+block_size
        tails+=((suffix+block_size-1)//block_size)*block_size
    return len(blocks)*block_size+tails


class ResidencyScheduler(AdmissionScheduler):
    def __init__(self,*,policy,residency_index,kv_capacity_tokens,max_bypasses=4,**kwargs):
        if policy not in RESIDENCY_POLICIES:raise ValueError(policy)
        super().__init__(policy='fifo',**kwargs)
        self.policy=policy;self.residency=residency_index
        self.kv_capacity_tokens=kv_capacity_tokens;self.max_bypasses=max_bypasses
        self._bypasses={}

    def _eligible(self,ticket,now):return True

    def _cpu_potential(self,ticket):
        return max((shared_prefix_tokens(ticket.engine_blocks,t.engine_blocks,block_size=16)
                    for t in self._recent),default=0)//256*256

    def _choose(self,now):
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
        gpu={t.request_id:self.residency.matched_tokens(t.engine_blocks) for t in self._queue}
        has_migration=any(self._cpu_potential(t)-gpu[t.request_id]>=1024 for t in self._queue)
        if self.policy=='residency' and not has_migration:
            oldest.dispatch_reason='no_migration_fifo';return oldest
        fitting=[t for t in self._queue if reserved_tokens([*active,t])<=self.kv_capacity_tokens]
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
