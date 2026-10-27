"""Synthetic event fixtures for the future real-prefix checker; no serving."""
import asyncio
import copy
import pytest
from cacheflow.scheduler import Ticket,AdmissionScheduler
from cacheflow.v3_residency import engine_block_hashes
from cacheflow.v6_ready_scheduler import ReadyUnionScheduler
from cacheflow.v7_epoch_scheduler import EpochReadyUnionScheduler
from cacheflow import v7_trace_states as module


def fixture(policy='packing_ready',ambiguous=False):
    engine=engine_block_hashes(list(range(1024)));blocks=tuple(b.hex() for b in engine)
    templates={rid:Ticket(request_id=rid,blocks=blocks,engine_blocks=engine,arrival_ns=0,enqueued_ns=0,deadline_ns=0,group='shared',input_tokens=1024,output_budget=96) for rid in ['a','b']}
    def row(rid,enq,dispatch,first,complete,reserved,reason):
        return dict(request_id=rid,run_id='synthetic',arrival_ns=enq,enqueue_ns=enq,dispatch_ns=dispatch,first_token_ns=first,complete_ns=complete,
            admission_deadline_ns=enq+200000000,status='ok',input_tokens=1024,prefix_group='shared',reserved_active_tokens=reserved,dispatch_reason=reason)
    first_reason='oldest_start' if policy=='packing_ready' else 'no_observed_prefix_reuse_fifo'
    follower_reason='oldest_ready_fits' if policy=='packing_ready' else 'oldest_fits'
    if not ambiguous:records=[row('a',1,2,5,10,1136,first_reason),row('b',3,6,7,11,1248,follower_reason)]
    else:
        # Record a dispatch order that cannot be recovered from timestamp queue
        # order. The checker must retain disagreement, not fake exact replay.
        records=[row('a',1,10,11,30,1248,follower_reason),row('b',2,5,6,20,1136,'ready_compatible_backfill' if policy=='packing_ready' else 'compatible_backfill')]
    settings=dict(scheduler=dict(policy=policy,max_inflight=16,max_queue=64,block_size=16,min_shared_tokens=1024,max_wait_ms=200),
        residency=dict(enabled=False,kv_capacity_tokens=4096,max_bypasses=8))
    return records,templates,settings


@pytest.mark.parametrize('policy',['packing_reuse','packing_ready'])
def test_membership_follows_recorded_events_and_original_prototype_match(policy):
    result=asyncio.run(module.compare_ledger_states(*fixture(policy),stride=1,polls=3))
    assert result['requests']==2 and result['events']==8 and result['prototype_winner_reason_timeout_mismatches']==0
    assert result['recorded_dispatch_agreements']==2 and result['recorded_reservation_mismatches']==0
    assert result['production_decision_trace_reproduced'] is False


@pytest.mark.parametrize('policy',['packing_reuse','packing_ready'])
def test_recorded_dispatch_disagreement_is_reported_without_changing_the_history(policy):
    result=asyncio.run(module.compare_ledger_states(*fixture(policy,True),stride=1))
    assert result['recorded_dispatch_mismatches']>0 and result['production_decision_trace_reproduced'] is False
    assert result['prototype_winner_reason_timeout_mismatches']==0 and result['recorded_reservation_mismatches']==0


def test_checker_detects_a_stale_none_readiness_bug(monkeypatch):
    class Broken(EpochReadyUnionScheduler):
        async def mark_first_token(self,ticket):await AdmissionScheduler.mark_first_token(self,ticket)
    monkeypatch.setitem(module.CLASSES,'packing_ready',(ReadyUnionScheduler,Broken))
    with pytest.raises(AssertionError,match='winner differs'):
        asyncio.run(module.compare_ledger_states(*fixture(),stride=1))


def test_changed_prefix_group_or_failed_record_cannot_pass_as_real_success():
    for key,bad in [('prefix_group','different'),('status','read_error')]:
        records,templates,settings=fixture();records[0][key]=bad
        with pytest.raises(AssertionError):asyncio.run(module.compare_ledger_states(records,templates,settings))
