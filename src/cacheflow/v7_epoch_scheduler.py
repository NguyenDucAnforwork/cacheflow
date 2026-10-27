"""Unactivated CPU prototype: versioned cache keys for unchanged V6 selectors.

No gateway factory imports this module. The running sealed study is untouched.
Only packing_reuse/packing_ready/ready_fifo are supported: their winner depends
on immutable ticket prompt/budget/deadline fields and lifecycle state, not now.
Private containers must not be replaced/reinitialized after construction.
"""
from __future__ import annotations

import time
from collections import deque
from functools import wraps
from .v3_memory_scheduler import ResidencyScheduler
from .v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler


def _mutates(method):
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        # Some bulk mutations can partially succeed before raising. Invalidate
        # even then; extra invalidation is safe, stale cache reuse is not.
        try:return method(self,*args,**kwargs)
        finally:self._changed()
    return wrapped


class _StateList(list):
    def __init__(self,values,changed):
        self._changed=changed;super().__init__(values)


class _StateDict(dict):
    def __init__(self,values,changed):
        self._changed=changed;super().__init__(values)


class _StateDeque(deque):
    def __init__(self,values,maxlen,changed):
        self._changed=changed;super().__init__(values,maxlen=maxlen)


for _kind,_base,_names in [
    (_StateList,list,['append','extend','insert','remove','pop','clear','reverse','sort','__setitem__','__delitem__','__iadd__','__imul__']),
    (_StateDict,dict,['__setitem__','__delitem__','clear','pop','popitem','setdefault','update','__ior__']),
    (_StateDeque,deque,['append','appendleft','extend','extendleft','insert','remove','pop','popleft','clear','reverse','rotate','__setitem__','__delitem__','__iadd__','__imul__']),
]:
    for _name in _names:setattr(_kind,_name,_mutates(getattr(_base,_name)))


class _EpochCache:
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        if self.policy not in {'packing_reuse','packing_ready','ready_fifo'}:raise ValueError(self.policy)
        self._epoch=0;self._queue_epoch=0;self._cached_epoch=-1;self._cached_winner=None
        self._deadline_epoch=-1;self._next_deadline=None;self._deadline_asof=None;self.timeout_recomputes=0
        self._queue=_StateList(self._queue,self._queue_changed)
        self._active=_StateDict(self._active,self._state_changed)
        self._recent=_StateDeque(self._recent,self._recent.maxlen,self._state_changed)
        self._bypasses=_StateDict(self._bypasses,self._state_changed)
        self._tracked=(self._queue,self._active,self._recent,self._bypasses)
        self._uncached_selector=self._choose_impl if self.policy=='packing_reuse' else self._choose_ready

    def _state_changed(self):self._epoch+=1

    def _queue_changed(self):
        self._epoch+=1;self._queue_epoch+=1

    def _check_state(self):
        queue,active,recent,bypasses=self._tracked
        if not (self._queue is queue and self._active is active and self._recent is recent and self._bypasses is bypasses):
            raise RuntimeError('Tracked lifecycle containers were replaced')

    def _choose(self,now):
        start=time.perf_counter_ns();cpu=time.thread_time_ns()
        try:
            self._check_state();epoch=self._epoch
            if epoch==self._cached_epoch:
                self.decision_cache_hits+=1;return self._cached_winner
            # Calls the original inherited algorithm, including its reservation,
            # readiness, reason and bounded-bypass rules. Never copy/tune it.
            winner=self._uncached_selector(now)
            self._cached_epoch=epoch;self._cached_winner=winner
            return winner
        finally:
            elapsed=time.perf_counter_ns()-start;self.decision_calls+=1
            self.decision_cpu_ns+=time.thread_time_ns()-cpu;self.decision_wall_ns+=elapsed
            self.decision_max_ns=max(self.decision_max_ns,elapsed)

    def _next_timeout(self,ticket,now):
        self._check_state()
        # These three policies have only queue deadlines in the original
        # timeout function. Recompute when membership/time horizon changes.
        if (self._deadline_epoch!=self._queue_epoch or self._deadline_asof is None or now<self._deadline_asof
            or (self._next_deadline is not None and now>=self._next_deadline)):
            self._next_deadline=min((t.deadline_ns for t in self._queue if t.deadline_ns>now),default=None)
            self._deadline_epoch=self._queue_epoch;self._deadline_asof=now;self.timeout_recomputes+=1
        return max(.001,(self._next_deadline-now)/1e9) if self._next_deadline is not None else .1

    async def mark_first_token(self,ticket):
        before=ticket.first_token_ns
        await super().mark_first_token(ticket)
        if self.policy!='packing_reuse' and ticket.first_token_ns!=before:self._state_changed()

    def decision_stats(self):
        return super().decision_stats()|dict(cache_key_kind='lifecycle_epoch_prototype',state_epoch=self._epoch,
            queue_epoch=self._queue_epoch,timeout_recomputes=self.timeout_recomputes)


class EpochUnionScheduler(_EpochCache,ResidencyScheduler):
    def __init__(self,*,policy='packing_reuse',**kwargs):
        if policy!='packing_reuse':raise ValueError(policy)
        super().__init__(policy=policy,**kwargs)


class EpochReadyUnionScheduler(_EpochCache,ReadyUnionScheduler):
    pass


class EpochReadyFifoScheduler(_EpochCache,ReadyFifoScheduler):
    pass
