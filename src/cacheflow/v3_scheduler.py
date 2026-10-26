"""Explicit cache-aware admission baselines, not full engine-paper reproductions."""
from __future__ import annotations

from .prefix import shared_prefix_tokens
from .scheduler import AdmissionScheduler, Ticket

V3_POLICIES = {'lpm_hint', 'bundle_wave'}


class BaselineScheduler(AdmissionScheduler):
    def __init__(self, *, policy: str, **kwargs):
        if policy not in V3_POLICIES:
            raise ValueError(policy)
        super().__init__(policy='fifo', **kwargs)
        self.policy = policy
        self._wave_count = 0
        self._wave_group = None

    def _eligible(self, ticket, now):
        return True

    def _choose(self, now):
        if len(self._active) >= self.max_inflight or not self._queue:
            return None
        if self.policy == 'lpm_hint':
            refs = list(self._active.values())
            if self._recent:
                refs.append(self._recent[-1])
            return max(self._queue, key=lambda t: max((shared_prefix_tokens(t.blocks, r.blocks,
                block_size=self.block_size) for r in refs), default=0))
        # Outer admission-wave adaptation of oldest-first bundle selection.
        # It does not reproduce Strata's layerwise I/O or engine batch formation.
        if not self._active:
            self._wave_count = 0
            self._wave_group = self._queue[0].group
        if self._wave_count >= self.max_inflight:
            return None
        matching = [t for t in self._queue if t.group and t.group == self._wave_group]
        chosen = matching[0] if matching else self._queue[0]
        return chosen

    async def admit(self, *args, **kwargs):
        ticket = await super().admit(*args, **kwargs)
        if self.policy == 'bundle_wave':
            self._wave_count += 1
        return ticket
