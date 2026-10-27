"""Explicit HMA-dispatch supplement; original CPU witness bytes retained.

The real connector implements SupportsHMA. The first CPU scaffold selected its
non-HMA fallback, which delegates to the same request_finished body. This tests
both native HMA dispatch and request_finished_all_groups too, without claiming
an actual connector constructor, multi-group allocator or GPU execution.
"""
import argparse
import json
from pathlib import Path
from types import MethodType
from unittest.mock import patch
import v11_transfer_lifetime_witness as witness
import v11_transfer_barrier_control as barrier
from v6_raw_archive import sha
from v8_allocation_witness import extract

ORIGINAL_STATE=witness.state


def hma_state(**kwargs):
    fixture=ORIGINAL_STATE(**kwargs);scheduler=fixture.scheduler;connector=scheduler.connector
    method,proof=extract(witness.CONNECTOR,'LMCacheMPConnector','request_finished_all_groups')
    connector.request_finished_all_groups=MethodType(method,connector);fixture.proofs.append(proof)
    # This method has its own compile/binding namespace for each fixture.
    scheduler._connector_finished.__func__.__globals__['SupportsHMA']=type(connector)
    assert isinstance(connector,scheduler._connector_finished.__func__.__globals__['SupportsHMA'])
    return fixture


def run():
    with patch.object(witness,'state',hma_state),patch.object(barrier,'state',hma_state):
        cases=[witness.scenario(order,repeat_terminal=repeat) for order in ['receive_late_no_store','store_first','receive_first','simultaneous'] for repeat in [False,True]]
        controls=[barrier.control(order,repeat,unhealthy=unhealthy) for order in ['receive_late_no_store','store_first','receive_first','simultaneous'] for repeat in [False,True] for unhealthy in [False,True]]
        positive=witness.positive_control();normal=barrier.normal_receive_control()
    return dict(kind='conditional_native_hma_transfer_lifetime_supplement',cpu_only=True,synthetic_metadata=True,gpu_execution=False,
        actual_native_connector_declares_supports_hma=True,cpu_fixture_selects_hma_dispatch=True,installed_files_modified=False,
        source_sha256={str(p):sha(p) for p in [Path(__file__),Path('scripts/v11_transfer_lifetime_witness.py'),Path('scripts/v11_transfer_barrier_control.py'),Path('src/cacheflow/v11_transfer_barrier.py')]},
        original_non_hma_witness_sha256=sha('results/v3/v11_transfer_lifetime_witness.json'),
        cases=cases,barrier_controls=controls,positive_control=positive,normal_receive_control=normal,
        scope='Same8conditional native-body failures and16barrier controls through HMA dispatch plus actual request_finished_all_groups body; one KV group of dummy block IDs. SupportsHMA type/constructor/queues/futures are CPU fixture bindings, not an actual native import/engine, arbitrary HMA tensor layout, live request chronology or earlier-stall reproduction. Original non-HMA scaffold and artifact remain unchanged; all transfer/barrier production assumptions and limitations still apply.')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);a=p.parse_args();value=run()
    with a.output.open('x') as out:out.write(json.dumps(value,indent=2)+'\n')
    print('HMA supplement8native-body cases/16barrier controls pass; no GPU/native activation',flush=True)
