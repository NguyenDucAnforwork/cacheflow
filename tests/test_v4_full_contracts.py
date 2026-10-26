from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
import json
from pathlib import Path
import pytest

spec=spec_from_file_location('v4_full_contracts','scripts/v4_full_contracts.py')
module=module_from_spec(spec);spec.loader.exec_module(module)
freeze=json.loads(Path('results/v3/v4_method_freeze.json').read_text())


def captured(arm):
    rid=f'v4c1-full-sg-g6-qps4-{arm}-s901'
    setup=json.loads(Path(f'results/v3/sglang/{rid}.setup.json').read_text())
    return dict(kind='sg',arm=arm,run_id=rid),setup


def test_captured_native_and_fifo_match_planned_semantics():
    for arm in ['native','fifo']:
        step,setup=captured(arm);module.audit_configuration(step,setup,freeze)


def test_mislabelled_arm_or_native_policy_is_rejected():
    step,setup=captured('fifo');step['arm']='union'
    with pytest.raises(AssertionError):module.audit_configuration(step,setup,freeze)
    step,setup=captured('native');setup['runtime']['schedule_policy']='dfs-weight'
    with pytest.raises(AssertionError):module.audit_configuration(step,setup,freeze)


def test_profiler_or_stale_gateway_state_cannot_pass_performance_contract():
    step,setup=captured('native');setup['public_server_env']['CACHEFLOW_SGLANG_TRANSFER_PROFILE']='1'
    with pytest.raises(AssertionError):module.audit_configuration(step,setup,freeze)
    step,setup=captured('fifo');setup['gateway_before']['completed_history_requests']=1
    with pytest.raises(AssertionError):module.audit_configuration(step,setup,freeze)
