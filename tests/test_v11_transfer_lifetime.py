"""Complete selected-native-body CPU fixtures, not live chronology or GPU proof."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v11_transfer_lifetime_witness as witness
import v11_transfer_barrier_control as control
from v11_hma_transfer_control import hma_state
from cacheflow.v11_transfer_barrier import TerminalTransferBarrier

ORDERS=['receive_late_no_store','store_first','receive_first','simultaneous']


@pytest.mark.parametrize('hma',[False,True])
@pytest.mark.parametrize('order',ORDERS)
@pytest.mark.parametrize('repeat',[False,True])
def test_conditional_original_native_completion_order_hazard(hma,order,repeat):
    constructor=hma_state if hma else witness.state
    with patch.object(witness,'state',constructor):result=witness.scenario(order,repeat_terminal=repeat)
    assert result['assertion']['line']==(2153 if order in {'receive_late_no_store','store_first'} else 2162)
    assert result['freed_while_operation_pending']==(order!='simultaneous')


@pytest.mark.parametrize('hma',[False,True])
@pytest.mark.parametrize('order',ORDERS)
@pytest.mark.parametrize('repeat',[False,True])
@pytest.mark.parametrize('unhealthy',[False,True])
def test_unactivated_barrier_retains_until_one_terminal_release(hma,order,repeat,unhealthy):
    constructor=hma_state if hma else witness.state
    with patch.object(control,'state',constructor):result=control.control(order,repeat,unhealthy=unhealthy)
    assert result['terminal_acknowledgements']==result['physical_free_callbacks']==1
    assert result['no_native_assertion'] and result['retained_terminal_tombstones']==1
    assert result['error_block_ids']==([1,2] if unhealthy else [])


def test_original_positive_control_and_nonterminal_receive_are_preserved():
    assert witness.positive_control()['exactly_one_safe_free']
    assert control.normal_receive_control()['nonterminal_receive_preserved']


def test_barrier_adds_no_future_poll_result_or_collector_call():
    original=witness.state(with_store=True);wrapped=witness.state(with_store=True);barrier=TerminalTransferBarrier()
    calls=[];native=wrapped.worker.get_finished
    wrapped.worker.get_finished=lambda values:(calls.append(set(values)) or native(values))
    for i,(receive,store) in enumerate([(False,False),(False,True),(True,True),(True,True)]):
        for fixture in [original,wrapped]:fixture.recv.ready=receive;fixture.store.ready=store
        finished={original.rid} if i==0 else set();saved=set(finished)
        original.worker.get_finished(finished);barrier.collect(wrapped.worker,finished)
        assert finished==saved
        assert (original.recv.queries,original.recv.results,original.store.queries,original.store.results)==(wrapped.recv.queries,wrapped.recv.results,wrapped.store.queries,wrapped.store.results)
    assert len(calls)==4 and not barrier.pending_terminal and barrier.acknowledged=={original.rid}


def test_late_registration_after_release_is_detected_instead_of_silently_accepted():
    fixture=witness.state();fixture.recv.ready=True;barrier=TerminalTransferBarrier()
    sending,receiving=barrier.collect(fixture.worker,{fixture.rid});assert sending=={fixture.rid} and not receiving
    fixture.worker.retrieve_futures[fixture.rid]=(witness.Future(),[1,2])
    with pytest.raises(AssertionError,match='registered after'):barrier.collect(fixture.worker,set())


def test_unseen_terminal_report_and_original_exception_fail_closed():
    barrier=TerminalTransferBarrier();worker=NS(retrieve_futures={},store_futures={},get_finished=lambda finished:({'unseen'},set()))
    with pytest.raises(AssertionError,match='unseen'):barrier.collect(worker,set())
    def failed(finished):raise RuntimeError('native-collector-fixture')
    worker.get_finished=failed
    with pytest.raises(RuntimeError,match='native-collector-fixture'):barrier.collect(worker,{'terminal'})
    assert not barrier.acknowledged and barrier.pending_terminal=={'terminal'}
