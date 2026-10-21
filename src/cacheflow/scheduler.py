"""Bounded ingress admission scheduler. It never modifies requests."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

from .prefix import group_digest, shared_prefix_tokens

Policy = Literal["fifo", "static_group", "dhas"]


@dataclass(slots=True)
class Ticket:
    request_id: str
    blocks: tuple[str, ...]
    arrival_ns: int
    enqueued_ns: int
    deadline_ns: int
    group: str | None
    dispatch_ns: int | None = None
    first_token_ns: int | None = None
    complete_ns: int | None = None
    cancellation_reason: str | None = None
    delay_hit_candidate: bool = False
    recent_match: bool = False


class AdmissionScheduler:
    def __init__(
        self,
        *,
        policy: Policy = "fifo",
        max_inflight: int = 16,
        max_queue: int = 64,
        max_wait_ms: int = 200,
        min_shared_tokens: int = 1024,
        block_size: int = 256,
        store_grace_ms: int = 20,
        group_window_ms: int = 30,
    ) -> None:
        if policy not in ("fifo", "static_group", "dhas"):
            raise ValueError(f"unknown policy {policy}")
        if min(max_inflight, max_queue, max_wait_ms, min_shared_tokens, block_size) <= 0:
            raise ValueError("capacities and thresholds must be positive")
        self.policy = policy
        self.max_inflight = max_inflight
        self.max_queue = max_queue
        self.max_wait_ns = max_wait_ms * 1_000_000
        self.min_shared_tokens = min_shared_tokens
        self.block_size = block_size
        self.store_grace_ns = store_grace_ms * 1_000_000
        self.group_window_ns = group_window_ms * 1_000_000
        self._condition = asyncio.Condition()
        self._queue: list[Ticket] = []
        self._active: dict[str, Ticket] = {}
        self._recent: deque[Ticket] = deque(maxlen=256)
        self._last_group: str | None = None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    @property
    def active_count(self) -> int:
        return len(self._active)

    def _matching_producer(self, ticket: Ticket) -> Ticket | None:
        if ticket.group is None:
            return None
        matches = (
            producer for producer in self._active.values()
            if producer.request_id != ticket.request_id
            and shared_prefix_tokens(ticket.blocks, producer.blocks, block_size=self.block_size)
            >= self.min_shared_tokens
        )
        return min(matches, key=lambda t: t.dispatch_ns or t.enqueued_ns, default=None)

    def _eligible(self, ticket: Ticket, now: int) -> bool:
        if self.policy == "fifo":
            return True
        if self.policy == "static_group":
            return len(self._queue) > 1 or now - ticket.enqueued_ns >= self.group_window_ns
        if now >= ticket.deadline_ns:
            return True
        producer = self._matching_producer(ticket)
        if producer is None:
            return True
        ticket.delay_hit_candidate = True
        return producer.first_token_ns is not None and now >= producer.first_token_ns + self.store_grace_ns

    def _choose(self, now: int) -> Ticket | None:
        if len(self._active) >= self.max_inflight:
            return None
        eligible = [ticket for ticket in self._queue if self._eligible(ticket, now)]
        if not eligible:
            return None
        if self.policy != "static_group":
            return eligible[0]
        oldest = eligible[0]
        if now >= oldest.deadline_ns:
            return oldest
        grouped = [t for t in eligible if t.group and t.group == self._last_group]
        return grouped[0] if grouped else oldest

    def _next_timeout(self, ticket: Ticket, now: int) -> float:
        deadlines = [t.deadline_ns for t in self._queue if t.deadline_ns > now]
        if self.policy == "static_group":
            deadlines += [t.enqueued_ns + self.group_window_ns for t in self._queue if t.enqueued_ns + self.group_window_ns > now]
        if self.policy == "dhas":
            deadlines += [t.first_token_ns + self.store_grace_ns for t in self._active.values()
                          if t.first_token_ns is not None and t.first_token_ns + self.store_grace_ns > now]
        return max(0.001, (min(deadlines) - now) / 1e9) if deadlines else 0.1

    async def admit(self, request_id: str, blocks: tuple[str, ...], *, arrival_ns: int | None = None) -> Ticket:
        arrival = arrival_ns or time.monotonic_ns()
        ticket = Ticket(
            request_id=request_id,
            blocks=blocks,
            arrival_ns=arrival,
            enqueued_ns=time.monotonic_ns(),
            deadline_ns=arrival + self.max_wait_ns,
            group=group_digest(blocks, min_shared_tokens=self.min_shared_tokens, block_size=self.block_size),
        )
        try:
            async with self._condition:
                while len(self._queue) >= self.max_queue:
                    await self._condition.wait()
                ticket.recent_match = any(
                    shared_prefix_tokens(blocks, old.blocks, block_size=self.block_size) >= self.min_shared_tokens
                    for old in self._recent
                )
                self._queue.append(ticket)
                self._condition.notify_all()
                while True:
                    now = time.monotonic_ns()
                    if self._choose(now) is ticket:
                        self._queue.remove(ticket)
                        ticket.dispatch_ns = now
                        self._active[request_id] = ticket
                        self._last_group = ticket.group
                        self._condition.notify_all()
                        return ticket
                    try:
                        await asyncio.wait_for(self._condition.wait(), timeout=self._next_timeout(ticket, now))
                    except TimeoutError:
                        pass
        except asyncio.CancelledError:
            async with self._condition:
                if ticket in self._queue:
                    self._queue.remove(ticket)
                ticket.cancellation_reason = "cancelled_before_dispatch"
                self._condition.notify_all()
            raise

    async def mark_first_token(self, ticket: Ticket) -> None:
        async with self._condition:
            if ticket.request_id in self._active and ticket.first_token_ns is None:
                ticket.first_token_ns = time.monotonic_ns()
                self._condition.notify_all()

    async def finish(self, ticket: Ticket, *, cancellation_reason: str | None = None) -> None:
        async with self._condition:
            self._active.pop(ticket.request_id, None)
            ticket.complete_ns = time.monotonic_ns()
            ticket.cancellation_reason = cancellation_reason
            if not cancellation_reason:
                self._recent.append(ticket)
            self._condition.notify_all()
