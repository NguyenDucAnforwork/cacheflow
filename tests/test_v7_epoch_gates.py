"""Projected prerequisite documents; never claim the queued jobs completed."""
import copy
import itertools
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v7_epoch_study as module
from v7_audit_epoch_dev import fresh_units
from v6_full_checkpoint import planned_pairs


def projected(monkeypatch):
    original=module.read('results/v3/v6full1_freeze.json')
    digest=lambda p:'projected-sha:'+str(p)
    cpu_reg=dict(policies=['packing_reuse','packing_ready','ready_fifo'],queues=[16,64,128,256,512],kernels=['chooser_hit','timeout_hit','poll_mutating'],rounds=5)
    targets=['v6full1-main-g6-union64-s901','v6full1-main-g6-packing_ready-s901']
    manifest=dict(files=[dict(path=f'copy{i}',sha256=digest(f'copy{i}')) for i in range(8)],actions=[{}]*30,
        reference_freeze_sha256=digest(module.BASE/'v6full1_freeze.json'),analysis_revision=dict(projected=True),protocol_path='copy-protocol',protocol_sha256=digest('copy-protocol'))
    records={str(module.BASE/'v7_epoch_cpu_probe_registration.json'):cpu_reg,str(module.BASE/'v7_epoch_trace_check_registration.json'):dict(target_run_ids=targets),'namespace-manifest':manifest}
    monkeypatch.setattr(module,'sha',digest);monkeypatch.setattr(module,'read',lambda p:records[str(p)])
    full=dict(complete=True,requests=59580,errors=0,unique_qa=1986,separate_warmup_requests=1800,pairs=[dict(a=a,b=b) for a,b in planned_pairs()],
        runs=[dict(run_id=r['run_id'],audit_sha256='audit',archive_sha256='archive') for r in original['actions']],
        process_units=dict(distinct_engine_pids=30,distinct_main_lmcache_pids=12),freeze_sha256=digest(module.BASE/'v6full1_freeze.json'))
    inp=dict(complete=True,cpu_only=True,registration_sha256=digest(module.BASE/'v6full1_input_regeneration_registration.json'),
        unique_qa=1986,answerable=1540,category5=446,input_tokens=50522325,prompt_and_token_fingerprints_equal=True,original_inputs_unchanged=True,seeds=[])
    paths={s['trace']:s['seed'] for s in original['actions']}
    for path,seed in paths.items():inp['seeds'].append(dict(seed=seed,original_path=path,requests=1986,generated_from_official_source=True,
        original_stored_sha256=original['input_file_sha256'][path],restored_identity=dict(stored_sha256=original['input_file_sha256'][path])))
    ns=dict(complete_namespace_preparation=True,gpu_execution=False,generated_cli_plan_equal=True,planned_fresh_arms=30,planned_measured_requests=59580,
        registration_sha256=digest(module.BASE/'v6full1_r1_namespace_preparation_registration.json'),source_input_reproduction_sha256=digest(module.PROOFS['inputs']),
        namespace_manifest_path='namespace-manifest',namespace_manifest_sha256=digest('namespace-manifest'))
    cases=[dict(policy=p,queue=q,kernel=k,samples={name:[dict(thread_cpu_ns_per_iteration=1.) for _ in range(5)] for name in ['legacy','prototype']}) for p,q,k in itertools.product(cpu_reg['policies'],cpu_reg['queues'],cpu_reg['kernels'])]
    cpu=dict(complete=True,synthetic=True,gpu_execution=False,registration_sha256=digest(module.BASE/'v7_epoch_cpu_probe_registration.json'),parent_result_sha256=digest(module.PROOFS['namespace']),cases=cases)
    trace=dict(complete_ledger_state_check=True,gpu_execution=False,production_decision_trace_reproduced=False,unique_qa=1986,input_tokens=50522325,request_trajectories=3972,
        registration_sha256=digest(module.BASE/'v7_epoch_trace_check_registration.json'),parent_result_sha256=digest(module.PROOFS['cpu']),terminal_full_audit_sha256=digest(module.PROOFS['full']),
        runs=[dict(run_id=rid,audit_sha256='audit',archive_sha256='archive',result=dict(requests=1986,events=7944,checked_state_points=2483,stable_polls_per_point=3,
            prototype_winner_reason_timeout_mismatches=0,prototype_active_reservation_mismatches=0,recorded_dispatch_mismatches=999)) for rid in targets])
    return dict(full=full,inputs=inp,namespace=ns,cpu=cpu,trace=trace),original


def test_projected_chain_and_nonexact_recorded_dispatch_diagnostic(monkeypatch):
    proofs,original=projected(monkeypatch);module.validate_prerequisites(proofs,original)


@pytest.mark.parametrize('bad',['full_incomplete','missing_full_arm','repeated_full_arm','missing_pair','duplicate_pair','partial_input','wrong_seed','namespace_unfinished',
    'cpu_unfinished','missing_cpu_case','duplicate_cpu_case','missing_cpu_round','nonfinite_cpu','trace_unfinished','trace_partial','logical_mismatch','missing_state_checks','wrong_trace_parent'])
def test_missing_partial_mismatched_proofs_cannot_open_gpu_gate(monkeypatch,bad):
    p,original=projected(monkeypatch)
    if bad=='full_incomplete':p['full']['complete']=False
    elif bad=='missing_full_arm':p['full']['runs'].pop()
    elif bad=='repeated_full_arm':p['full']['runs'][-1]=copy.deepcopy(p['full']['runs'][0])
    elif bad=='missing_pair':p['full']['pairs'].pop()
    elif bad=='duplicate_pair':p['full']['pairs'][-1]=copy.deepcopy(p['full']['pairs'][0])
    elif bad=='partial_input':p['inputs']['unique_qa']=2
    elif bad=='wrong_seed':p['inputs']['seeds'][0]['seed']=123
    elif bad=='namespace_unfinished':p['namespace']['complete_namespace_preparation']=False
    elif bad=='cpu_unfinished':p['cpu']['complete']=False
    elif bad=='missing_cpu_case':p['cpu']['cases'].pop()
    elif bad=='duplicate_cpu_case':p['cpu']['cases'][-1]=copy.deepcopy(p['cpu']['cases'][0])
    elif bad=='missing_cpu_round':p['cpu']['cases'][0]['samples']['legacy'].pop()
    elif bad=='nonfinite_cpu':p['cpu']['cases'][0]['samples']['legacy'][0]['thread_cpu_ns_per_iteration']=float('nan')
    elif bad=='trace_unfinished':p['trace']['complete_ledger_state_check']=False
    elif bad=='trace_partial':p['trace']['request_trajectories']=2
    elif bad=='logical_mismatch':p['trace']['runs'][0]['result']['prototype_winner_reason_timeout_mismatches']=1
    elif bad=='missing_state_checks':p['trace']['runs'][0]['result']['checked_state_points']=0
    else:p['trace']['parent_result_sha256']='wrong'
    with pytest.raises(AssertionError):module.validate_prerequisites(p,original)


def test_terminal_development_rejects_retained_or_missing_process_units():
    runs=[dict(step=dict(engine='main' if i<9 else 'sg'),engine_pid=1000+i,lmcache_pid=2000+i if i<9 else None) for i in range(18)]
    assert fresh_units(runs)==dict(distinct_engine_pids=18,distinct_main_lmcache_pids=9)
    for change in ['engine','cache','missing_cache','native_cache']:
        bad=copy.deepcopy(runs)
        if change=='engine':bad[-1]['engine_pid']=bad[0]['engine_pid']
        elif change=='cache':bad[1]['lmcache_pid']=bad[0]['lmcache_pid']
        elif change=='missing_cache':bad[0]['lmcache_pid']=None
        else:bad[-1]['lmcache_pid']=999
        with pytest.raises(AssertionError):fresh_units(bad)
