"""Unactivated completion-barrier prototype for CPU lifecycle experiments.

No import hook, worker monkeypatch or serving entrypoint installs this class.
Requires a fresh wrapper and all transfers registered before terminal delivery;
request IDs cannot be reused. It does not establish those engine assumptions.
"""
from __future__ import annotations


class TerminalTransferBarrier:
    """Emit one terminal acknowledgement after registered operations quiesce.

    Calls the original completion collector exactly once and never queries,
    waits on or synchronizes a future/event itself. Already-terminal requests
    use one finished_sending acknowledgement, withholding finished_recving.
    Nonterminal completion semantics pass through. Tombstones are unbounded in
    this prototype; production lifetime/epoch reclamation is not implemented.
    """

    def __init__(self):
        self.terminal_seen=set()
        self.pending_terminal=set()
        self.acknowledged=set()

    def collect(self,worker,finished_from_engine):
        finished=set(finished_from_engine)
        self.terminal_seen.update(finished)
        self.pending_terminal.update(finished-self.acknowledged)
        self._check_no_later_operations(worker)
        # The caller supplies an unwrapped, already-bound native method.
        raw_sending,raw_receiving=worker.get_finished(finished)
        sending=set(raw_sending or ())
        receiving=set(raw_receiving or ())
        assert sending<=self.terminal_seen,'Collector returned an unseen terminal ID'
        self._check_no_later_operations(worker)
        # Native collector may have acknowledged a store while a retrieve is
        # pending. Its dedup bookkeeping is left intact; the explicit barrier
        # remembers our still-pending terminal acknowledgement independently.
        ready={rid for rid in self.pending_terminal
            if rid not in worker.retrieve_futures and rid not in worker.store_futures}
        sending.difference_update(self.terminal_seen)
        receiving.difference_update(self.terminal_seen)
        sending.update(ready)
        self.pending_terminal.difference_update(ready)
        self.acknowledged.update(ready)
        return sending,receiving

    def _check_no_later_operations(self,worker):
        assert not (self.acknowledged & (worker.retrieve_futures.keys() | worker.store_futures.keys())), 'Transfer registered after terminal acknowledgement; prototype contract violated'
