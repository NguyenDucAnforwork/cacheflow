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


def test_guard_bypasses_wait_when_measured_producer_is_too_slow():
    async def run():
        scheduler = AdmissionScheduler(policy="dhas_guarded", max_inflight=2, max_wait_ms=20,
                                       min_shared_tokens=8, block_size=4, store_grace_ms=0)
        first_group = prefix_blocks(list(range(16)), block_size=4)
        second_group = prefix_blocks(list(range(100, 116)), block_size=4)
        warm_producer = await scheduler.admit("warm-producer", first_group)
        await asyncio.sleep(0.05)
        await scheduler.mark_first_token(warm_producer)
        await scheduler.finish(warm_producer)
        producer = await scheduler.admit("producer", second_group)
        follower = await asyncio.wait_for(scheduler.admit("follower", second_group), 0.1)
        assert follower.delay_hit_candidate
        assert follower.readiness_guard_bypassed
        assert follower.readiness_estimate_ms is not None
        assert follower.readiness_estimate_ms > 20
        await scheduler.finish(producer)
        await scheduler.finish(follower)
    asyncio.run(run())


def test_class_first_admits_chat_before_older_doc():
    async def run():
        scheduler = AdmissionScheduler(policy="class_first", max_inflight=1, max_wait_ms=500,
                                       min_shared_tokens=8, block_size=4)
        busy = await scheduler.admit("busy", prefix_blocks(list(range(16)), block_size=4), priority=1)
        doc = asyncio.create_task(scheduler.admit("doc", prefix_blocks(list(range(100, 116)), block_size=4), priority=1))
        await asyncio.sleep(0.01)
        chat = asyncio.create_task(scheduler.admit("chat", prefix_blocks(list(range(200, 216)), block_size=4), priority=0))
        await asyncio.sleep(0.01)
        await scheduler.finish(busy)
        first = await asyncio.wait_for(asyncio.wait({doc, chat}, return_when=asyncio.FIRST_COMPLETED), 0.5)
        assert chat in first[0] and doc not in first[0]
        await scheduler.finish(chat.result())
        await scheduler.finish(await asyncio.wait_for(doc, 0.5))
    asyncio.run(run())


def test_class_aged_promotes_old_doc_over_chat():
    async def run():
        scheduler = AdmissionScheduler(policy="class_aged", max_inflight=1, max_wait_ms=500,
                                       min_shared_tokens=8, block_size=4, age_cap_ms=100)
        busy = await scheduler.admit("busy", prefix_blocks(list(range(16)), block_size=4), priority=1)
        doc = asyncio.create_task(scheduler.admit("doc", prefix_blocks(list(range(100, 116)), block_size=4), priority=1))
        await asyncio.sleep(0.2)  # the doc is now older than the 100 ms age cap
        chat = asyncio.create_task(scheduler.admit("chat", prefix_blocks(list(range(200, 216)), block_size=4), priority=0))
        await asyncio.sleep(0.01)
        await scheduler.finish(busy)
        first = await asyncio.wait_for(asyncio.wait({doc, chat}, return_when=asyncio.FIRST_COMPLETED), 0.5)
        assert doc in first[0] and chat not in first[0]
        assert doc.result().promoted
        await scheduler.finish(doc.result())
        await scheduler.finish(await asyncio.wait_for(chat, 0.5))
    asyncio.run(run())


def test_class_aged_young_doc_waits_for_chat():
    async def run():
        scheduler = AdmissionScheduler(policy="class_aged", max_inflight=1, max_wait_ms=500,
                                       min_shared_tokens=8, block_size=4, age_cap_ms=5000)
        busy = await scheduler.admit("busy", prefix_blocks(list(range(16)), block_size=4), priority=1)
        doc = asyncio.create_task(scheduler.admit("doc", prefix_blocks(list(range(100, 116)), block_size=4), priority=1))
        await asyncio.sleep(0.01)
        chat = asyncio.create_task(scheduler.admit("chat", prefix_blocks(list(range(200, 216)), block_size=4), priority=0))
        await asyncio.sleep(0.01)
        await scheduler.finish(busy)
        first = await asyncio.wait_for(asyncio.wait({doc, chat}, return_when=asyncio.FIRST_COMPLETED), 0.5)
        assert chat in first[0] and doc not in first[0]
        assert not chat.result().promoted
        await scheduler.finish(chat.result())
        await scheduler.finish(await asyncio.wait_for(doc, 0.5))
    asyncio.run(run())


def _slack_case(wait_s: float, tokens: int, expect_doc_first: bool):
    async def run():
        scheduler = AdmissionScheduler(policy="class_slack", max_inflight=1, max_wait_ms=500, min_shared_tokens=8,
                                       block_size=4, doc_slo_ms=1000, ms_per_1k_tokens=100.0, slack_margin_ms=100)
        busy = await scheduler.admit("busy", prefix_blocks(list(range(16)), block_size=4), priority=1)
        doc = asyncio.create_task(scheduler.admit("doc", prefix_blocks(list(range(100, 116)), block_size=4), priority=1, input_tokens=tokens))
        await asyncio.sleep(wait_s)
        chat = asyncio.create_task(scheduler.admit("chat", prefix_blocks(list(range(200, 216)), block_size=4), priority=0))
        await asyncio.sleep(0.01)
        await scheduler.finish(busy)
        first = await asyncio.wait_for(asyncio.wait({doc, chat}, return_when=asyncio.FIRST_COMPLETED), 0.5)
        assert (doc in first[0]) == expect_doc_first
        winner = doc.result() if expect_doc_first else chat.result()
        loser = chat if expect_doc_first else doc
        await scheduler.finish(winner)
        await scheduler.finish(await asyncio.wait_for(loser, 0.5))
    asyncio.run(run())


def test_class_slack_promotes_doc_when_slack_is_gone():
    # slo 1000 ms, 5000 tokens x 100 ms/1k = 500 ms service, 100 ms margin: promote after 400 ms of waiting
    _slack_case(wait_s=0.5, tokens=5000, expect_doc_first=True)


def test_class_slack_keeps_chat_first_while_slack_remains():
    _slack_case(wait_s=0.05, tokens=5000, expect_doc_first=False)
