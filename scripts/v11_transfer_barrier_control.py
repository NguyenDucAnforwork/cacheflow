"""Native-body CPU controls for an unactivated terminal completion barrier."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace as NS
from cacheflow.v11_transfer_barrier import TerminalTransferBarrier
from v6_raw_archive import sha
from v11_transfer_lifetime_witness import state


def control(order,repeat_terminal=False,*,unhealthy=False):
    fixture=state(with_store=order!='receive_late_no_store');s,w=fixture.scheduler,fixture.worker;rid=fixture.rid
    assert s.finish_requests(rid,fixture.Status.FINISHED_ABORTED)==[(rid,0)]
    barrier=TerminalTransferBarrier();rounds=[];acknowledgements=0
    if order=='receive_late_no_store':steps=[(False,None),(True,None),(True,None)]
    elif order=='store_first':steps=[(False,True),(True,True),(True,True)]
    elif order=='receive_first':steps=[(True,False),(True,True),(True,True)]
    elif order=='simultaneous':steps=[(True,True),(True,True)]
    else:raise ValueError(order)
    for i,(r_ready,s_ready) in enumerate(steps):
        fixture.recv.ready=r_ready
        if fixture.store is not None:fixture.store.ready=s_ready
        w.is_healthy=not unhealthy
        sending,receiving=barrier.collect(w,{rid} if i==0 or repeat_terminal else set())
        assert not receiving and sending<= {rid}
        acknowledgements+=int(rid in sending)
        s._update_from_kv_xfer_finished(NS(finished_sending=sending,finished_recving=receiving))
        # Unhealthy native collector explicitly drains failed operations without
        # reporting successful tensor transfer; no actual DMA is simulated.
        pending=bool(w.retrieve_futures or w.store_futures)
        if pending:assert rid in s.requests and not fixture.freed
        rounds.append(dict(round=i,operations_pending=pending,finished_sending=sorted(sending),finished_recving=sorted(receiving),request_retained=rid in s.requests))
    assert rid not in s.requests and len(fixture.freed)==acknowledgements==1
    if not unhealthy:assert all(not row['receive_pending'] and not row['store_pending'] for row in fixture.freed)
    return dict(order=order,repeat_terminal_signal=repeat_terminal,unhealthy_drain=unhealthy,rounds=rounds,
        terminal_acknowledgements=acknowledgements,physical_free_callbacks=len(fixture.freed),no_native_assertion=True,
        receive_queries=fixture.recv.queries,store_queries=fixture.store.queries if fixture.store else None,
        retained_terminal_tombstones=len(barrier.acknowledged),
        error_block_ids=sorted(w.error_block_ids))


def normal_receive_control():
    fixture=state();s,w=fixture.scheduler,fixture.worker;rid=fixture.rid
    barrier=TerminalTransferBarrier();fixture.recv.ready=True
    sending,receiving=barrier.collect(w,set())
    assert receiving=={rid} and not sending
    s._update_from_kv_xfer_finished(NS(finished_sending=sending,finished_recving=receiving))
    assert rid in s.requests and rid in s.finished_recving_kv_req_ids and not fixture.freed
    return dict(nonterminal_receive_preserved=True,request_blocks_retained=True,receive_queries=fixture.recv.queries)


def run():
    original=Path('results/v3/v11_transfer_lifetime_witness.json');assert original.exists()
    cases=[control(order,repeat,unhealthy=unhealthy) for order in ['receive_late_no_store','store_first','receive_first','simultaneous'] for repeat in [False,True] for unhealthy in [False,True]]
    return dict(kind='unactivated_terminal_transfer_barrier_cpu_controls',cpu_only=True,synthetic_metadata=True,gpu_execution=False,installed_files_modified=False,
        source_sha256={str(p):sha(p) for p in [Path(__file__),Path('src/cacheflow/v11_transfer_barrier.py'),Path('scripts/v11_transfer_lifetime_witness.py')]},
        original_conditional_witness_sha256=sha(original),cases=cases,normal_receive_control=normal_receive_control(),
        scope='Sixteen complete selected-native-body CPU controls; all registered operations quiesce or native unhealthy-drain completes before one terminal release. No extra future queries/results/event synchronization beyond original collector. All transfer registrations precede terminal delivery and IDs are not reused; those full-engine assumptions, allocator/tensor safety, bounded tombstone memory, remote cancellation/IPC races, runtime activation, earlier-stall mitigation, full correctness/quality/fairness/performance and competitive contribution remain unproved.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();value=run()
    with a.output.open('x') as out:out.write(json.dumps(value,indent=2)+'\n')
    print('16unactivated barrier CPU controls pass; no serving or liveness fix claim',flush=True)
