import asyncio
import time
from cacheflow.v3_residency import ResidencyIndex,engine_block_hashes
from cacheflow.v6_ready_scheduler import ReadyUnionScheduler,ReadyFifoScheduler


def make(cls=ReadyUnionScheduler,**kwargs):
    return cls(residency_index=ResidencyIndex(),kv_capacity_tokens=4096,max_inflight=16,
               block_size=16,min_shared_tokens=1024,max_bypasses=kwargs.pop('max_bypasses',8),**kwargs)


async def admit(s,rid,tag=0):
    hashes=engine_block_hashes(list(range(tag,tag+1024)))
    return await s.admit(rid,tuple(h.hex() for h in hashes),engine_blocks=hashes,input_tokens=1024,output_budget=96)


def test_pending_prefix_stays_blocked_then_readiness_invalidates_cached_decision():
    async def scenario():
        s=make();producer=await admit(s,'producer');task=asyncio.create_task(admit(s,'follower'));await asyncio.sleep(.01)
        assert not task.done();assert s._choose(time.monotonic_ns()) is None
        old_hits=s.decision_cache_hits;assert s._choose(time.monotonic_ns()) is None;assert s.decision_cache_hits>old_hits
        await s.mark_first_token(producer);follower=await asyncio.wait_for(task,1)
        assert follower.dispatch_reason=='oldest_ready_fits'
        third=asyncio.create_task(admit(s,'third'));await asyncio.sleep(.01)
        assert not third.done(), 'A ready producer must not allow two additional unready followers'
        await s.mark_first_token(follower);await asyncio.wait_for(third,1)
    asyncio.run(scenario())


def test_distinct_prefixes_can_progress_and_bypasses_stay_bounded():
    async def scenario():
        s=make(max_bypasses=1);producer=await admit(s,'producer')
        old=asyncio.create_task(admit(s,'old'));await asyncio.sleep(.01)
        backfill=await asyncio.wait_for(admit(s,'other',5000),1)
        assert backfill.scheduler_head_id=='old' and s._bypasses['old']==1 and not old.done()
        next_other=asyncio.create_task(admit(s,'another',10000));await asyncio.sleep(.01);assert not next_other.done()
        await s.finish(producer,cancellation_reason='test-cancel')
        await asyncio.wait_for(old,1);await asyncio.wait_for(next_other,1)
    asyncio.run(scenario())


def test_cancelled_queued_follower_does_not_hold_progress():
    async def scenario():
        s=make();producer=await admit(s,'producer');follower=asyncio.create_task(admit(s,'follower'));await asyncio.sleep(.01)
        follower.cancel()
        try:await follower
        except asyncio.CancelledError:pass
        assert not s._queue and 'follower' not in s._bypasses
        await s.finish(producer);await asyncio.wait_for(admit(s,'next'),1)
    asyncio.run(scenario())


def test_short_shared_system_prefix_does_not_trigger_gate():
    async def scenario():
        s=make();first=list(range(1024));second=[*range(128),*range(5000,5896)]
        async def send(rid,tokens):
            h=engine_block_hashes(tokens)
            return await s.admit(rid,tuple(x.hex() for x in h),engine_blocks=h,input_tokens=1024,output_budget=96)
        await send('one',first);await asyncio.wait_for(send('two',second),1)
    asyncio.run(scenario())


def test_gate_only_ablation_ignores_union_budget_but_keeps_same_readiness_rule():
    async def scenario():
        s=ReadyFifoScheduler(residency_index=ResidencyIndex(),kv_capacity_tokens=1024,max_inflight=16,block_size=16,min_shared_tokens=1024)
        producer=await admit(s,'one');await asyncio.wait_for(admit(s,'other',5000),1)
        follower=asyncio.create_task(admit(s,'follower'));await asyncio.sleep(.01);assert not follower.done()
        await s.mark_first_token(producer);await asyncio.wait_for(follower,1)
    asyncio.run(scenario())


def test_opt_in_factory_keeps_parent_policy_constructor_and_is_process_local():
    import subprocess,sys
    script='''
from cacheflow import v3_memory_scheduler as m
from cacheflow.v3_residency import ResidencyIndex
from cacheflow.v6_gateway import install_admission_adapter
parent=m.ResidencyScheduler
install_admission_adapter();first=m.ResidencyScheduler;install_admission_adapter()
assert m.ResidencyScheduler is first
args=dict(residency_index=ResidencyIndex(),kv_capacity_tokens=4096)
assert type(m.ResidencyScheduler(policy='packing_reuse',**args)) is parent
assert type(m.ResidencyScheduler(policy='packing_ready',**args)).__name__=='ReadyUnionScheduler'
assert type(m.ResidencyScheduler(policy='ready_fifo',**args)).__name__=='ReadyFifoScheduler'
'''
    subprocess.run([sys.executable,'-c',script],check=True)


def test_replay_extension_changes_only_policy_enumeration_and_launch_target():
    import subprocess,sys
    from pathlib import Path
    assert Path('src/cacheflow/v6_replay.py').read_text()==Path('src/cacheflow/v2_replay.py').read_text().replace('"sglang_dfs-weight"]','"sglang_dfs-weight", "ready_fifo", "packing_ready"]')
    assert Path('scripts/v6_v2_run.sh').read_text()==Path('scripts/v2_run.sh').read_text().replace('python -m cacheflow.v2_replay','python -m cacheflow.v6_replay')
    assert Path('scripts/v6_run.sh').read_text()==Path('scripts/v3_run.sh').read_text().replace('bash scripts/v2_run.sh','bash scripts/v6_v2_run.sh')
    for policy in ['ready_fifo','packing_ready']:
        subprocess.run([sys.executable,'-m','cacheflow.v6_replay','--policy',policy,'--help'],check=True,stdout=subprocess.DEVNULL)
