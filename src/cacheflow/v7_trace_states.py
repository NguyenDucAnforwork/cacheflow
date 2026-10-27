"""Compare selectors on ledger-derived lifecycle states, never infer GPU speed.

Enqueue timestamps precede condition-lock acquisition and head IDs/wakeups were
not logged. Dispatch/reservation agreement is diagnostic, not proof that this
reconstruction is the original internal decision trace.
"""
from collections import Counter
from dataclasses import replace
from .v3_residency import ResidencyIndex
from .v3_memory_scheduler import ResidencyScheduler,reserved_tokens
from .v6_ready_scheduler import ReadyUnionScheduler
from .v7_epoch_scheduler import EpochUnionScheduler,EpochReadyUnionScheduler

CLASSES={'packing_reuse':(ResidencyScheduler,EpochUnionScheduler),'packing_ready':(ReadyUnionScheduler,EpochReadyUnionScheduler)}
BACKFILL={'compatible_backfill','ready_compatible_backfill','ready_fifo_backfill'}


async def compare_ledger_states(records,templates,settings,*,stride=16,polls=3):
    assert stride>0 and polls>0 and records
    cfg=settings['scheduler'];policy=cfg['policy'];assert policy in CLASSES and not settings['residency']['enabled']
    states=[cls(**cfg,residency_index=ResidencyIndex(),kv_capacity_tokens=settings['residency']['kv_capacity_tokens'],
        max_bypasses=settings['residency']['max_bypasses']) for cls in CLASSES[policy]]
    by={r['request_id']:r for r in records};assert len(by)==len(records) and by.keys()==templates.keys()
    tickets=[{},{}];events=[]
    for rid,row in by.items():
        assert row['status']=='ok' and row['input_tokens']==templates[rid].input_tokens
        assert row['prefix_group']==templates[rid].group,'Real prefix-group preparation differs'
        times=[row[k] for k in ['enqueue_ns','dispatch_ns','first_token_ns','complete_ns']]
        assert all(isinstance(t,int) for t in times) and all(a<=b for a,b in zip(times,times[1:]))
        for order,(kind,stamp) in enumerate(zip(['enqueue','dispatch','first','finish'],times)):events.append((stamp,order,rid,kind))
    events.sort();multiplicity=Counter(t for t,_,_,_ in events)
    points=0;dispatch_mismatches=[];reservation_mismatches=[];inferred_head_ambiguities=0;peak_queue=0;peak_active=0
    def point(now):
        nonlocal points
        choices=[]
        for _ in range(polls):
            a,b=[s._choose(now) for s in states]
            assert (a.request_id if a else None)==(b.request_id if b else None),'Prototype winner differs on ledger-derived state'
            if a:assert (a.dispatch_reason,a.scheduler_head_id)==(b.dispatch_reason,b.scheduler_head_id),'Prototype reason/head differs'
            assert states[0]._next_timeout(None,now)==states[1]._next_timeout(None,now),'Prototype timeout differs'
            choices.append(a.request_id if a else None)
        points+=1;return choices[0]
    for index,(now,_,rid,kind) in enumerate(events):
        row=by[rid]
        if kind=='enqueue':
            for s,ts in zip(states,tickets):
                t=replace(templates[rid],arrival_ns=row['arrival_ns'],enqueued_ns=row['enqueue_ns'],deadline_ns=row['admission_deadline_ns'],
                    recent_match=bool(row.get('recent_match',False)))
                ts[rid]=t;s._queue.append(t)
        elif kind=='dispatch':
            predicted=point(now)
            if predicted!=rid:dispatch_mismatches.append(dict(request_id=rid,predicted=predicted,timestamp_ns=now))
            heads=[s._queue[0].request_id for s in states];assert heads[0]==heads[1]
            backfill=row['dispatch_reason'] in BACKFILL
            if (backfill and heads[0]==rid) or (not backfill and heads[0]!=rid):inferred_head_ambiguities+=1
            # Follow recorded membership changes on BOTH models; never branch
            # the state history according to whichever selector is preferable.
            for s,ts in zip(states,tickets):
                t=ts[rid];s._queue.remove(t);t.dispatch_ns=now;t.dispatch_reason=row['dispatch_reason'];s._active[rid]=t;s._last_group=t.group
                head=heads[0] if backfill and heads[0]!=rid else None
                t.scheduler_head_id=head
                if head:s._bypasses[head]=s._bypasses.get(head,0)+1
                else:s._bypasses.pop(rid,None)
            reservation=[reserved_tokens(s._active.values()) for s in states];assert reservation[0]==reservation[1]
            if reservation[0]!=row['reserved_active_tokens']:
                reservation_mismatches.append(dict(request_id=rid,recorded=row['reserved_active_tokens'],reconstructed=reservation[0]))
        elif kind=='first':
            for s,ts in zip(states,tickets):
                await s.mark_first_token(ts[rid])
                # Original pure selectors depend on readiness Boolean, not the
                # numeric first-text timestamp. Restore the recorded timestamp.
                ts[rid].first_token_ns=now
        else:
            for s,ts in zip(states,tickets):
                await s.finish(ts[rid]);ts[rid].complete_ns=now
        if index%stride==0:point(now)
        assert [t.request_id for t in states[0]._queue]==[t.request_id for t in states[1]._queue]
        assert list(states[0]._active)==list(states[1]._active) and states[0]._bypasses==states[1]._bypasses
        peak_queue=max(peak_queue,len(states[0]._queue));peak_active=max(peak_active,len(states[0]._active))
    assert all(not s._queue and not s._active for s in states)
    return dict(requests=len(records),events=len(events),checked_state_points=points,stable_polls_per_point=polls,
        prototype_winner_reason_timeout_mismatches=0,prototype_active_reservation_mismatches=0,
        recorded_dispatch_agreement_unit='request_id only; missing wakeup/head/lock history is not recovered',recorded_dispatch_agreements=len(records)-len(dispatch_mismatches),recorded_dispatch_mismatches=len(dispatch_mismatches),
        first_recorded_dispatch_mismatches=dispatch_mismatches[:20],recorded_reservation_mismatches=len(reservation_mismatches),
        first_recorded_reservation_mismatches=reservation_mismatches[:20],inferred_head_ambiguities=inferred_head_ambiguities,
        equal_timestamp_events=sum(n for n in multiplicity.values() if n>1),reconstructed_queue_peak=peak_queue,reconstructed_active_peak=peak_active,
        production_decision_trace_reproduced=False,
        scope='Logical original/prototype parity on ledger-derived states using real prefix templates; recorded membership is followed even when the predicted dispatch differs. Condition-lock append order, head IDs and actual wakeup calls were not captured. Agreement does not recover missing internal events, timing/CPU saved, GPU behavior, quality equivalence or production liveness.')
