import asyncio
from types import SimpleNamespace

from cacheflow.scheduler import Ticket
from cacheflow.v3_memory_scheduler import ResidencyScheduler, reserved_tokens
from cacheflow.v3_residency import ResidencyIndex, engine_block_hashes


def event(kind, **values):
    return type(kind, (), {})(**values) if not values else type(kind, (), values)()


def test_residency_counts_clear_and_sequence_loss():
    index = ResidencyIndex()
    keys = engine_block_hashes(list(range(48)))
    index.apply(1, [event('AllBlocksCleared')])
    index.apply(2, [event('BlockStored', block_hashes=[keys[0], keys[0], keys[1]], medium='GPU')])
    index.apply(3, [event('BlockRemoved', block_hashes=[keys[0]], medium='GPU')])
    assert index.matched_tokens(keys) == 32
    index.apply(4, [event('BlockRemoved', block_hashes=[keys[0]], medium='GPU')])
    assert index.matched_tokens(keys) == 0
    index.apply(6, [event('BlockStored', block_hashes=keys, medium='GPU')])
    assert not index.known and index.gaps == 1 and index.matched_tokens(keys) == 0
    index.apply(7, [event('AllBlocksCleared')])
    assert index.known and not index.refs
    index.apply(8, [event('BlockStored', block_hashes=keys, medium='CPU')])
    assert not index.refs


def test_reservation_shared_prefix_and_output_bounds():
    a = engine_block_hashes(list(range(64)))
    b = engine_block_hashes([*range(32), *range(100,132)])
    def t(blocks):
        return SimpleNamespace(engine_blocks=blocks, input_tokens=67, output_budget=17)
    # Six distinct input blocks plus two rounded (3-tail +17-output+16-safety) suffixes.
    assert reserved_tokens([t(a),t(b)]) == 6*16+2*48
    assert reserved_tokens([t(a),t(a)]) == 4*16+2*48


def test_packing_backfill_guard_and_drain_progress():
    async def scenario():
        index = ResidencyIndex(); index.known = True
        scheduler = ResidencyScheduler(policy='packing_fifo',residency_index=index,
            kv_capacity_tokens=256,max_inflight=4,max_bypasses=1,
            block_size=16,min_shared_tokens=16)
        a=engine_block_hashes(list(range(160)))
        b=engine_block_hashes(list(range(500,660)))
        async def admit(name,blocks):
            return await scheduler.admit(name,tuple(x.hex() for x in blocks),
                engine_blocks=blocks,input_tokens=160,output_budget=16)
        active=await admit('active',a)
        old=asyncio.create_task(admit('old',b))
        await asyncio.sleep(.005)
        back=await asyncio.wait_for(admit('backfill',a),1)
        assert back.dispatch_reason=='compatible_backfill' and not old.done()
        later=asyncio.create_task(admit('later',a))
        await asyncio.sleep(.005)
        assert not later.done()  # guard drains even compatible work
        await scheduler.finish(active)
        await scheduler.finish(back)
        first=await asyncio.wait_for(old,1)
        assert first.request_id=='old'
        assert not later.done()
        await scheduler.finish(first)
        last=await asyncio.wait_for(later,1)
        await scheduler.finish(last)
        assert scheduler.active_count==scheduler.queue_depth==0
    asyncio.run(scenario())


def test_unknown_residency_keeps_fifo():
    async def scenario():
        scheduler=ResidencyScheduler(policy='residency',residency_index=ResidencyIndex(),
            kv_capacity_tokens=16,max_inflight=2)
        a=await scheduler.admit('a',())
        b=await scheduler.admit('b',())
        assert a.dispatch_reason==b.dispatch_reason=='unknown_residency_fifo'
        await scheduler.finish(a);await scheduler.finish(b)
    asyncio.run(scenario())


def test_live_event_contract_accepts_bytes_rejects_legacy_ints():
    import pytest
    from cacheflow.v3_residency import verify_event_hash_contract
    tokens=list(range(32));keys=engine_block_hashes(tokens)
    values=dict(block_size=16,block_hashes=keys,parent_block_hash=None,
                token_ids=tokens,extra_keys=[None,None])
    verify_event_hash_contract(SimpleNamespace(**values))
    values['block_hashes']=[int.from_bytes(keys[0],'big') & ((1<<64)-1)]
    with pytest.raises(ValueError,match='INT_BLOCK_HASHES'):
        verify_event_hash_contract(SimpleNamespace(**values))
    values['block_hashes']=[b'x'*32]
    with pytest.raises(ValueError,match='hash contract differs'):
        verify_event_hash_contract(SimpleNamespace(**values))


def test_incremental_reservation_matches_full_union_for_shared_and_distinct_blocks():
    import random
    from cacheflow.v3_memory_scheduler import incremental_reservation, reservation_state
    rng=random.Random(73)
    for _ in range(100):
        def ticket():
            blocks=tuple(rng.randrange(12).to_bytes(2,'big') for _ in range(rng.randrange(8)))
            return SimpleNamespace(engine_blocks=blocks,input_tokens=len(blocks)*16+rng.randrange(16),
                                   output_budget=rng.choice([0,16,17,96]))
        active=[ticket() for _ in range(rng.randrange(1,6))];new=ticket()
        blocks,tails=reservation_state(active)
        optimized=incremental_reservation(blocks,len(blocks)*16+tails,new)
        assert optimized==reserved_tokens([*active,new])


def test_packing_decision_cache_invalidates_queue_active_and_guard_changes():
    import time
    index=ResidencyIndex();index.known=True
    scheduler=ResidencyScheduler(policy='packing_fifo',residency_index=index,
        kv_capacity_tokens=256,max_inflight=4,max_bypasses=1,block_size=16,min_shared_tokens=16)
    def t(name,start):
        blocks=engine_block_hashes(list(range(start,start+160)))
        return Ticket(request_id=name,blocks=(),arrival_ns=1,enqueued_ns=1,deadline_ns=2,group=name,
            engine_blocks=blocks,input_tokens=160,output_budget=16)
    active=t('active',0);head=t('head',500);back=t('back',0)
    scheduler._active={'active':active};scheduler._queue=[head,back]
    assert scheduler._choose(time.monotonic_ns()) is back
    assert scheduler._choose(time.monotonic_ns()) is back
    assert scheduler.decision_cache_hits==1
    scheduler._bypasses['head']=1
    assert scheduler._choose(time.monotonic_ns()) is None
    scheduler._active.clear()
    assert scheduler._choose(time.monotonic_ns()) is head
    scheduler._queue.remove(head)
    assert scheduler._choose(time.monotonic_ns()) is back
    index.known=False
    assert scheduler._choose(time.monotonic_ns()).dispatch_reason=='unknown_residency_fifo'


def test_lpm_cached_choice_invalidates_when_kv_event_sequence_changes():
    import time
    index=ResidencyIndex()
    a=engine_block_hashes(list(range(32)))
    b=engine_block_hashes(list(range(100,132)))
    index.apply(1,[event('AllBlocksCleared'),event('BlockStored',block_hashes=a,medium='GPU')])
    scheduler=ResidencyScheduler(policy='lpm_real',residency_index=index,
        kv_capacity_tokens=256,max_inflight=4)
    def t(name,blocks):
        return Ticket(request_id=name,blocks=(),arrival_ns=1,enqueued_ns=1,deadline_ns=2,group=None,
            engine_blocks=blocks,input_tokens=32,output_budget=16)
    qa=t('a',a);qb=t('b',b);scheduler._queue=[qa,qb]
    assert scheduler._choose(time.monotonic_ns()) is qa
    assert scheduler._choose(time.monotonic_ns()) is qa
    index.apply(2,[event('BlockRemoved',block_hashes=a,medium='GPU'),
                   event('BlockStored',block_hashes=b,medium='GPU')])
    assert scheduler._choose(time.monotonic_ns()) is qb


def test_pure_packing_ignores_observer_bootstrap_and_reuse_gate_keeps_cold_fifo():
    import time
    def t(name,group,start):
        keys=engine_block_hashes(list(range(start,start+160)))
        return Ticket(request_id=name,blocks=(),arrival_ns=1,enqueued_ns=1,deadline_ns=2,group=group,
            engine_blocks=keys,input_tokens=160,output_budget=16)
    active=t('a','group-a',0);head=t('b','group-b',500);back=t('c','group-a',0)
    for policy in ['packing','packing_reuse']:
        s=ResidencyScheduler(policy=policy,residency_index=ResidencyIndex(),
            kv_capacity_tokens=256,max_inflight=4)
        s._active={'a':active};s._queue=[head,back]
        chosen=s._choose(time.monotonic_ns())
        assert chosen is (back if policy=='packing' else head)
        if policy=='packing_reuse':
            s._recent.append(t('completed','group-a',0))
            assert s._choose(time.monotonic_ns()) is back
