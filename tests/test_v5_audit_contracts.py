from copy import deepcopy
from importlib.util import spec_from_file_location,module_from_spec
import json
from pathlib import Path
import pytest

spec=spec_from_file_location('v5_audit_contracts_test','scripts/v5_audit_contracts.py')
module=module_from_spec(spec);spec.loader.exec_module(module)


def captured():
    seal=json.loads(Path('results/v3/v5_prompt_freeze.json').read_text())
    parent=json.loads(Path('results/v3/v4_method_freeze.json').read_text())
    parent['source_sha256'].update({k:v for k,v in seal['source_sha256'].items() if k in parent['source_sha256']})
    rid='v5r2-dev-lpm-g6-qps4-fifo-s101'
    row=next(r for r in json.loads(Path('results/v3/v5r2_primary_sg_audit.json').read_text())['runs'] if r['run_id']==rid)
    summary=dict(row,successes=row['requests'],source_sha256=parent['source_data_sha256'],output_tokens_budget=96,
        client_keepalive_connections=0,request_read_timeout_s=3600,request_pool_timeout_s=3600)
    setup=json.loads(Path(f'results/v3/sglang/{rid}.setup.json').read_text())
    manifest=json.loads(Path('results/v3/trace_v5-dev4b3-qps4-s101.manifest.json').read_text())
    return dict(run_id=rid,kind='sg',arm='fifo'),setup,summary,manifest,parent,seal


def test_recorded_configuration_has_complete_source_and_transport_evidence():
    module.audit_common(*captured())


def test_source_fingerprint_coverage_cannot_be_silently_omitted():
    values=list(captured());del values[1]['frontend_source_sha256']['src/cacheflow/v2_replay.py']
    with pytest.raises(AssertionError,match='missing source-fingerprint evidence'):module.audit_common(*values)


def test_client_transport_must_match_the_revision2_control():
    values=list(captured());values[2]['client_keepalive_connections']=20
    with pytest.raises(AssertionError):module.audit_common(*values)
