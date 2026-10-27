"""CPU tests of V10 proof boundaries; no V10 inference/performance evidence."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v10_epoch_native as native
import v10_epoch_study as study
from v10_epoch_plan import build_plan
from v6_raw_archive import sha

ROOT=Path.cwd()


def test_matrix_has_same_native_intervention_on_all_main_baselines_and_candidates():
    rows=build_plan();assert len(rows)==len({r['run_id'] for r in rows})==18
    for seed in [101,102,103]:
        subset=[r for r in rows if r['seed']==seed]
        assert {(r['engine'],r['arm']) for r in subset}=={('main',a) for a in ['bundle16','union64','epoch_union64']}|{('sg',a) for a in ['native_dfs','union64','epoch_union64']}
        for row in subset:
            assert row['requests']==row['warmup_requests']==60 and not row['probe']
            assert row['mode']==('idempotent' if row['engine']=='main' else None)
    study.source_proof()


def test_actual_input_namespace_cpu_and_revised_trace_proofs_pass_without_forging_original_full(monkeypatch):
    # Only future repair audit is a stub here. Every other document is real and
    # retains original complete=false/failedfull. This is not GPU gate approval.
    proofs={k:study.read(p) for k,p in study.PROOFS.items() if k not in {'repair','repair_registration','repair_terminal'}}
    proofs.update(repair={},repair_registration={},repair_terminal={})
    monkeypatch.setattr(native,'validate_repair',lambda *args:None)
    study.validate_prerequisites(proofs,study.read(ROOT/'results/v3/v6full1_freeze.json'))
    assert proofs['full']['complete'] is False and proofs['failed_full']['errors']==1013
    proofs['trace']['runs'][0]['result']['prototype_winner_reason_timeout_mismatches']=1
    with pytest.raises(AssertionError):study.validate_prerequisites(proofs,study.read(ROOT/'results/v3/v6full1_freeze.json'))


def fixture(tmp_path,monkeypatch):
    original=json.loads((ROOT/'results/v3/v9repair2-probe-idempotent-s101.native_identity.json').read_text())
    monkeypatch.chdir(tmp_path);raw=tmp_path/'results/v3/raw';raw.mkdir(parents=True)
    before=copy.deepcopy(original['before']);before['checked_monotonic_ns']=100
    after=copy.deepcopy(before);after['checked_monotonic_ns']=300
    rows=before['constructor_records']
    for row in rows:row['monotonic_ns']=50
    path=raw/'fixture-native.1.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
    before['proof_sha256']={str(path):sha(path)};after['proof_sha256']=copy.deepcopy(before['proof_sha256'])
    after['constructor_records']=copy.deepcopy(rows)
    record=dict(before=before,after=after)
    step=dict(mode='idempotent',probe=False,proof_label='fixture-native')
    freeze=dict(native_method_expected=dict(idempotent={k:rows[0][k] for k in ['mode','effective_method_code_sha256','functional_replacements']}))
    return step,record,[dict(client_send_ns=150,complete_ns=250)],freeze,path


def test_actual_constructor_proof_shape_and_window_are_accepted(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch);assert native.validate_identity(*args[:4])


@pytest.mark.parametrize('bad',['mode','probe','birth','code','before_clock','after_clock','file','membership','role','prefix'])
def test_tampered_native_identity_cannot_enter_epoch_audit(tmp_path,monkeypatch,bad):
    step,record,rows,freeze,path=fixture(tmp_path,monkeypatch)
    if bad=='mode':record['after']['mode']='reference'
    elif bad=='probe':step['probe']=True
    elif bad=='birth':record['after']['engine_birth']+=1
    elif bad=='code':freeze['native_method_expected']['idempotent']['effective_method_code_sha256']='changed'
    elif bad=='before_clock':record['before']['checked_monotonic_ns']=200
    elif bad=='after_clock':record['after']['checked_monotonic_ns']=200
    elif bad=='file':path.write_text(path.read_text()+'\n')
    elif bad=='membership':record['before']['constructor_records'].pop()
    elif bad=='role':
        for side in ['before','after']:
            for row in record[side]['constructor_records']:row['connector_role']='KVConnectorRole.SCHEDULER'
    elif bad=='prefix':step['proof_label']='unrelated'
    with pytest.raises(AssertionError):native.validate_identity(step,record,rows,freeze)


def test_engine_launch_uses_identical_native_mode_without_prefix_collision():
    step=next(r for r in build_plan() if r['engine']=='main')
    original=f'command={Path.cwd()}/scripts/v2_serve_vllm.sh\nenvironment=EXISTING="1"\n'
    freeze=dict(repair_native_source_sha256={str(native.SOURCE):sha(native.SOURCE)})
    result=native.engine_config(original,step,freeze)
    assert 'v9_serve_vllm.sh' in result and 'CACHEFLOW_V9_WATERMARK_MODE="idempotent"' in result
    assert 'CACHEFLOW_V9_ENABLE_PROBE="0"' in result and 'CACHEFLOW_V8_LIVENESS_LOG' not in result
    assert step['run_id']+'-engine.log' in result and step['run_id']+'.engine.log' not in result
    assert 'EXISTING="1"' in result
    with pytest.raises(AssertionError):native.engine_config(result,step,freeze)


def repair_fixture(tmp_path,monkeypatch):
    import v9_repair_r1
    monkeypatch.chdir(tmp_path);base=tmp_path/'results/v3';base.mkdir(parents=True)
    monkeypatch.setattr(v9_repair_r1,'verify',lambda registration:None)
    (base/'v9repair2_registration.json').write_text('{}')
    terminal=dict(diagnostic_execution_complete=True,error=None,cleanup_errors=[],registration_sha256=sha(base/'v9repair2_registration.json'),outcomes=[])
    audit=dict(complete_repair_diagnostic_audit=True,performance_valid=False,research_complete=False,
        registration_sha256=terminal['registration_sha256'],target_requests=8064,separate_warmups=360,distinct_engines=6,distinct_cpu_caches=6,runs=[],full_pairs=[])
    for step in v9_repair_r1.plan():
        rid=step['run_id'];quality=base/(rid+'.quality.json');quality.write_text('{}')
        probe=dict(eligible_sampled_prefetch_states=1,distinct_inflated_ids=int(step['mode']=='reference')) if step['probe'] else None
        detail=dict(step=step,quality_sha256=sha(quality),probe=probe)
        path=base/(rid+'.repair_audit.json');path.write_text(json.dumps(detail))
        row=dict(run_id=rid,requests=step['requests'],errors=0,audit_sha256=sha(path),quality_sha256=sha(quality),probe=probe)
        audit['runs'].append(row);terminal['outcomes'].append({k:row[k] for k in ['run_id','requests','errors','audit_sha256']})
    for seed in [901,902]:audit['full_pairs'].append(dict(seed=seed,reference=f'v9repair2-full-reference-s{seed}',idempotent=f'v9repair2-full-idempotent-s{seed}',reference_errors=0,idempotent_errors=0,quality_and_work_comparison={}))
    path=base/'v9repair2_terminal.json';path.write_text(json.dumps(terminal));audit['terminal_sha256']=sha(path)
    return audit,terminal,{}


def test_entire_diagnostic_gate_accepts_successful_graph(tmp_path,monkeypatch):
    native.validate_repair(*repair_fixture(tmp_path,monkeypatch))


def test_failed_full_outcome_is_retained_without_subset_quality_or_false_liveness_gate(tmp_path,monkeypatch):
    audit,terminal,registration=repair_fixture(tmp_path,monkeypatch)
    row=audit['runs'][3];outcome=terminal['outcomes'][3];row['errors']=outcome['errors']=1000
    row['quality_sha256']=None
    path=Path('results/v3')/(row['run_id']+'.repair_audit.json');detail=json.loads(path.read_text());detail['quality_sha256']=None;path.write_text(json.dumps(detail))
    row['audit_sha256']=outcome['audit_sha256']=sha(path)
    path=Path('results/v3/v9repair2_terminal.json');path.write_text(json.dumps(terminal));audit['terminal_sha256']=sha(path)
    audit['full_pairs'][0].update(idempotent_errors=1000,quality_and_work_comparison=None)
    native.validate_repair(audit,terminal,registration)
    audit['full_pairs'][0]['quality_and_work_comparison']={}
    with pytest.raises(AssertionError):native.validate_repair(audit,terminal,registration)


@pytest.mark.parametrize('bad',['incomplete','missing_run','reused_engine','errors_in_probe','inflation_candidate','zero_reference','missing_pair','wrong_requests'])
def test_projected_repair_gate_rejects_invalid_or_partial_evidence(tmp_path,monkeypatch,bad):
    audit,terminal,registration=repair_fixture(tmp_path,monkeypatch)
    if bad=='incomplete':terminal['diagnostic_execution_complete']=False
    elif bad=='missing_run':audit['runs'].pop()
    elif bad=='reused_engine':audit['distinct_engines']=5
    elif bad=='errors_in_probe':audit['runs'][0]['errors']=terminal['outcomes'][0]['errors']=1
    elif bad=='inflation_candidate':audit['runs'][1]['probe']['distinct_inflated_ids']=1
    elif bad=='zero_reference':audit['runs'][0]['probe']['distinct_inflated_ids']=0
    elif bad=='missing_pair':audit['full_pairs'].pop()
    elif bad=='wrong_requests':audit['target_requests']=8000
    with pytest.raises(AssertionError):native.validate_repair(audit,terminal,registration)
