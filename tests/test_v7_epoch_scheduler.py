"""CPU-only prototype equivalence/cancellation/cache-work tests, no GPU results."""
import asyncio
import copy
import random
import time
import pytest
from cacheflow.scheduler import Ticket,AdmissionScheduler
from cacheflow.v3_memory_scheduler import ResidencyScheduler
from cacheflow.v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler
from cacheflow.v3_residency import ResidencyIndex,engine_block_hashes
from cacheflow.v7_epoch_scheduler import EpochUnionScheduler,EpochReadyUnionScheduler,EpochReadyFifoScheduler,_StateList,_StateDict,_StateDeque

PAIRS=[(ResidencyScheduler,EpochUnionScheduler,'packing_reuse'),(ReadyUnionScheduler,EpochReadyUnionScheduler,'packing_ready'),(ReadyFifoScheduler,EpochReadyFifoScheduler,'ready_fifo')]


def make(cls,policy,**kwargs):
    return cls(policy=policy,residency_index=ResidencyIndex(),kv_capacity_tokens=4096,max_inflight=kwargs.pop('max_inflight',16),
        block_size=16,min_shared_tokens=1024,max_bypasses=kwargs.pop('max_bypasses',8),**kwargs)


def ticket(rid,group,now,tail=0):
    ids=[*range(group*5000,group*5000+1024),*([100000+rid]*tail)]
    blocks=engine_block_hashes(ids)
    return Ticket(request_id=f'r{rid}',blocks=tuple(b.hex() for b in blocks),arrival_ns=now,enqueued_ns=now,deadline_ns=now+200000000,
        group=f'g{group}',engine_blocks=blocks,input_tokens=len(ids),output_budget=96)


def commit_dispatch(s,winner,now):
    s._queue.remove(winner);winner.dispatch_ns=now;s._active[winner.request_id]=winner;s._last_group=winner.group
    if winner.scheduler_head_id and winner.scheduler_head_id!=winner.request_id:
        head=winner.scheduler_head_id;s._bypasses[head]=s._bypasses.get(head,0)+1
    else:s._bypasses.pop(winner.request_id,None)


@pytest.mark.parametrize('legacy_cls,fast_cls,policy',PAIRS)
def test_randomized_same_event_trace_preserves_winner_reason_bypass_and_timeout(legacy_cls,fast_cls,policy):
    async def scenario():
        legacy=make(legacy_cls,policy);fast=make(fast_cls,policy)
        assert fast._uncached_selector.__func__ is (legacy_cls._choose_impl if policy=='packing_reuse' else legacy_cls._choose_ready)
        rng=random.Random(719);now=1000000000;counter=0
        for step in range(600):
            now+=rng.randrange(1,10000000);event=rng.randrange(6)
            if event<=1 and len(legacy._queue)<32:
                new=ticket(counter,rng.randrange(4),now,rng.choice([0,7,16,31]));counter+=1
                legacy._queue.append(new);fast._queue.append(copy.deepcopy(new))
            elif event==2 and legacy._active:
                rid=rng.choice(list(legacy._active))
                await legacy.mark_first_token(legacy._active[rid]);await fast.mark_first_token(fast._active[rid])
            elif event==3 and legacy._active:
                rid=rng.choice(list(legacy._active));cancel='fixture-cancel' if rng.randrange(3)==0 else None
                await legacy.finish(legacy._active[rid],cancellation_reason=cancel)
                await fast.finish(fast._active[rid],cancellation_reason=cancel)
            elif event==4 and legacy._queue:
                rid=rng.choice(legacy._queue).request_id
                for s in [legacy,fast]:
                    s._queue.remove(next(t for t in s._queue if t.request_id==rid));s._bypasses.pop(rid,None)
            for _ in range(3):
                a=legacy._choose(now);b=fast._choose(now)
                assert (a.request_id if a else None)==(b.request_id if b else None)
                if a:assert (a.dispatch_reason,a.scheduler_head_id)==(b.dispatch_reason,b.scheduler_head_id)
                assert legacy._bypasses==fast._bypasses
                assert legacy._next_timeout(None,now)==fast._next_timeout(None,now)
            if a and rng.randrange(2):
                commit_dispatch(legacy,a,now);commit_dispatch(fast,b,now)
            assert list(legacy._active)==list(fast._active) and [t.request_id for t in legacy._queue]==[t.request_id for t in fast._queue]
        assert counter>100 and fast.decision_cache_hits>0
    asyncio.run(scenario())


@pytest.mark.parametrize('legacy_cls,fast_cls,policy',PAIRS)
def test_cached_hits_do_not_iterate_lifecycle_containers(legacy_cls,fast_cls,policy,monkeypatch):
    s=make(fast_cls,policy);now=1000000000
    s._queue.extend([ticket(i,i%4,now) for i in range(128)])
    winner=s._choose(now);expected=[AdmissionScheduler._next_timeout(s,None,now+i) for i in range(20)];s._next_timeout(None,now)
    def forbid(*args,**kwargs):raise AssertionError('Stable cache hit traversed a lifecycle container')
    with monkeypatch.context() as patch:
        for cls in [_StateList,_StateDict,_StateDeque]:patch.setattr(cls,'__iter__',forbid)
        for advance in range(20):
            assert s._choose(now+advance) is winner
            assert s._next_timeout(None,now+advance)==expected[advance]
    s._queue.remove(winner)
    assert s._choose(now).request_id!=winner.request_id


def test_deadline_cache_expires_and_handles_clock_reversal_queue_mutation_and_partial_failure():
    old=make(ResidencyScheduler,'packing_reuse');new=make(EpochUnionScheduler,'packing_reuse')
    for s in [old,new]:s._queue.extend([ticket(1,0,1000000000),ticket(2,1,1200000000)])
    for now in [1000000000,1199999999,1200000000,1300000000,1400000000,1700000000,1100000000]:
        assert old._next_timeout(None,now)==new._next_timeout(None,now)
    version=new._queue_epoch
    def broken():
        yield ticket(3,2,1800000000)
        raise RuntimeError('Partial append fixture')
    with pytest.raises(RuntimeError):new._queue.extend(broken())
    assert new._queue_epoch>version and new._queue[-1].request_id=='r3'
    old._queue.append(copy.deepcopy(new._queue[-1]))
    assert new._next_timeout(None,1700000000)==old._next_timeout(None,1700000000)==.3
    new._queue=[]
    with pytest.raises(RuntimeError,match='containers were replaced'):new._choose(1800000000)


@pytest.mark.parametrize('cls,policy',[(EpochReadyUnionScheduler,'packing_ready'),(EpochReadyFifoScheduler,'ready_fifo')])
def test_real_async_first_text_and_queued_cancellation_release_cached_none(cls,policy):
    async def scenario():
        s=make(cls,policy,max_bypasses=1)
        async def send(rid,group):
            t=ticket(rid,group,time.monotonic_ns())
            return await s.admit(t.request_id,t.blocks,engine_blocks=t.engine_blocks,input_tokens=t.input_tokens,output_budget=t.output_budget)
        producer=await send(0,0);pending=asyncio.create_task(send(1,0));await asyncio.sleep(.005)
        assert not pending.done();assert s._choose(time.monotonic_ns()) is None
        other=await asyncio.wait_for(send(2,1),1);assert other.scheduler_head_id=='r1' and s._bypasses['r1']==1
        next_other=asyncio.create_task(send(3,2));await asyncio.sleep(.005);assert not next_other.done()
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        assert 'r1' not in s._bypasses
        await asyncio.wait_for(next_other,1)
        follower=asyncio.create_task(send(4,0));await asyncio.sleep(.005);assert not follower.done()
        await s.mark_first_token(producer);admitted=await asyncio.wait_for(follower,1)
        assert admitted.request_id=='r4'
        await s.finish(admitted,cancellation_reason='fixture')
        assert s.decision_stats()['cache_key_kind']=='lifecycle_epoch_prototype'
    asyncio.run(scenario())


def test_union_real_async_cap_and_cancellation_restore_progress():
    async def scenario():
        s=make(EpochUnionScheduler,'packing_reuse',max_inflight=1)
        async def send(rid):
            t=ticket(rid,0,time.monotonic_ns())
            return await s.admit(t.request_id,t.blocks,engine_blocks=t.engine_blocks,input_tokens=t.input_tokens,output_budget=t.output_budget)
        active=await send(0);pending=asyncio.create_task(send(1));await asyncio.sleep(.005);assert not pending.done()
        assert s._choose(time.monotonic_ns()) is None;pending.cancel()
        with pytest.raises(asyncio.CancelledError):await pending
        following=asyncio.create_task(send(2));await asyncio.sleep(.005);assert not following.done()
        await s.finish(active);assert (await asyncio.wait_for(following,1)).request_id=='r2'
    asyncio.run(scenario())


def test_prototype_does_not_replace_parent_or_enable_other_policies():
    from cacheflow import v3_memory_scheduler as original
    assert original.ResidencyScheduler is ResidencyScheduler
    with pytest.raises(ValueError):make(EpochUnionScheduler,'lpm_real')
    s=make(EpochUnionScheduler,'packing_reuse');assert s._epoch==s._queue_epoch==0
    assert s._choose_impl.__func__ is ResidencyScheduler._choose_impl


def test_union_first_text_is_not_an_unnecessary_cache_dependency():
    async def scenario():
        s=make(EpochUnionScheduler,'packing_reuse');active=ticket(0,0,1);s._active[active.request_id]=active;s._queue.append(ticket(1,0,1))
        winner=s._choose(1);epoch=s._epoch;hits=s.decision_cache_hits
        await s.mark_first_token(active)
        assert s._epoch==epoch and s._choose(2) is winner and s.decision_cache_hits==hits+1
    asyncio.run(scenario())


def test_partial_bulk_mutation_cannot_reuse_a_cached_empty_queue():
    s=make(EpochUnionScheduler,'packing_reuse');assert s._choose(1) is None
    def broken():
        yield ticket(0,0,1)
        raise RuntimeError('Partial mutation')
    with pytest.raises(RuntimeError):s._queue.extend(broken())
    assert s._choose(2).request_id=='r0'
