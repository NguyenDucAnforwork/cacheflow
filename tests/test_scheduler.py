import asyncio
import time

from cacheflow.prefix import prefix_blocks
from cacheflow.scheduler import AdmissionScheduler


def test_dhas_defers_follower_but_not_unrelated_request():
    async def run():
        scheduler = AdmissionScheduler(policy="dhas", max_inflight=3, max_wait_ms=500,
                                       min_shared_tokens=8, block_size=4, store_grace_ms=0)
        shared = prefix_blocks(list(range(16)), block_size=4)
        other = prefix_blocks(list(range(100, 116)), block_size=4)
        lead = await scheduler.admit("lead", shared)
        follower = asyncio.create_task(scheduler.admit("follower", shared))
        await asyncio.sleep(0.02)
        assert not follower.done()
        unrelated = await asyncio.wait_for(scheduler.admit("unrelated", other), 0.2)
        assert unrelated.dispatch_ns is not None
        await scheduler.mark_first_token(lead)
        admitted = await asyncio.wait_for(follower, 0.2)
        assert admitted.delay_hit_candidate
        await scheduler.finish(lead)
        await scheduler.finish(unrelated)
        await scheduler.finish(admitted)
    asyncio.run(run())


def test_dhas_hard_wait_limit_and_cancellation():
    async def run():
        scheduler = AdmissionScheduler(policy="dhas", max_inflight=2, max_wait_ms=30,
                                       min_shared_tokens=8, block_size=4, store_grace_ms=0)
        blocks = prefix_blocks(list(range(16)), block_size=4)
        lead = await scheduler.admit("lead", blocks)
        started = time.monotonic()
        follower = await asyncio.wait_for(scheduler.admit("follower", blocks), 0.3)
        assert time.monotonic() - started >= 0.02
        await scheduler.finish(follower)
        pending = asyncio.create_task(scheduler.admit("pending", blocks))
        await asyncio.sleep(0.005)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        assert scheduler.queue_depth == 0
        await scheduler.finish(lead)
    asyncio.run(run())
