import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_freeze_full import lowreuse_gates


def audits():
    # The native producer is a real complete audit. Main values below are
    # projected gate fixtures only, never evidence of a main control result.
    native=json.loads(Path('results/v3/sglang/v6native1_audit.json').read_text())
    main=dict(complete=True,errors=0,pairs=[dict(regime='lowreuse',baseline='fifo64',candidate=c,seed=s,
        p95_ms_delta_pct=v) for c in ['union64','packing_ready'] for s,v in [(103,5),(101,0),(102,-1)]])
    return dict(main=main,sg=native)


def test_gate_reads_both_actual_producer_schemas_and_sorts_seeds():
    data=audits();gates=lowreuse_gates(data)
    assert gates['main_union64']['per_seed_p95_delta_pct']==[0,-1,5]
    assert gates['main_union64']['source_metric']=='p95_ms_delta_pct'
    assert gates['sg_union64']['source_metric']=='p95_delta_pct'
    assert all(g['passes'] and g['seeds']==[101,102,103] for g in gates.values())
    # Feeding the native field name to the main parser must not silently pass.
    for row in data['main']['pairs']:row['p95_delta_pct']=row.pop('p95_ms_delta_pct')
    with pytest.raises(KeyError):lowreuse_gates(data)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),None,True])
def test_gate_rejects_unknown_nonfinite_and_boolean_deltas(value):
    data=audits();data['main']['pairs'][0]['p95_ms_delta_pct']=value
    with pytest.raises(AssertionError):lowreuse_gates(data)


def test_gate_requires_each_seed_and_complete_audit():
    original=audits()
    for mutate in [lambda a:a['main'].update(complete=False),lambda a:a['main'].update(errors=1),
                   lambda a:a['main']['pairs'].pop(),lambda a:a['main']['pairs'][0].update(seed=101)]:
        data=copy.deepcopy(original);mutate(data)
        with pytest.raises(AssertionError):lowreuse_gates(data)


def test_primary_failure_blocks_but_readiness_failure_remains_an_ablation():
    data=audits();data['main']['pairs'][0]['p95_ms_delta_pct']=5.0001
    with pytest.raises(AssertionError,match='Original-union'):lowreuse_gates(data)
    data=audits()
    next(r for r in data['main']['pairs'] if r['candidate']=='packing_ready')['p95_ms_delta_pct']=6
    gates=lowreuse_gates(data)
    assert gates['main_union64']['passes'] and not gates['main_packing_ready']['passes']
