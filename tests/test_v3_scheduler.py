import asyncio

from cacheflow.v3_scheduler import BaselineScheduler


def test_bundle_wave_progress_with_multiple_waiters():
    async def scenario():
        scheduler=BaselineScheduler(policy='bundle_wave',max_inflight=2,min_shared_tokens=1,block_size=1)
        initial=[await scheduler.admit('initial-a',('a',)),await scheduler.admit('initial-b',('b',))]
        pending=[asyncio.create_task(scheduler.admit(f'q{i}',('a' if i%2 else 'b',))) for i in range(8)]
        await asyncio.sleep(.01)
        for ticket in initial: await scheduler.finish(ticket)
        while pending:
            done,rest=await asyncio.wait(pending,timeout=1,return_when=asyncio.FIRST_COMPLETED)
            assert done,'queued work deadlocked despite free capacity'
            for task in done: await scheduler.finish(task.result())
            pending=list(rest)
        assert scheduler.active_count==0 and scheduler.queue_depth==0
    asyncio.run(scenario())
