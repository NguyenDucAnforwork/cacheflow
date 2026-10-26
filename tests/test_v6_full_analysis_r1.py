"""Analysis repair must preserve real configuration and every integrity check."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
import v6_full_analysis_r1 as revision
from v6_full_contracts import audit_configuration as original
from v5_verify import verify
from v6_raw_archive import sha


def test_last_scalar_value_matches_argparse_store_semantics():
    flags={'--max-num-seqs'}
    assert revision.scalar_argv(['serve','--max-num-seqs','4','--max-num-seqs=16'],flags)==['serve','--max-num-seqs','16']
    assert revision.scalar_argv(['--max-num-seqs=16','--max-num-seqs','4'],flags)==['--max-num-seqs','4']
    for argv in [[],['--max-num-seqs'],['--max-num-seqs','--other'],['--max-num-seqs=x']]:
        with pytest.raises(AssertionError):revision.scalar_argv(argv,flags)


@pytest.fixture
def real_raw():
    from contextlib import nullcontext
    from v6_raw_archive import expanded
    archive=Path('results/v3/v6full1-main-g6-fifo64-s901.archive_r1.json')
    with expanded(archive) if archive.exists() else nullcontext():yield


def test_real_captured_main_contract_and_wrong_effective_value(real_raw):
    parent,seal=verify();freeze=json.loads(Path('results/v3/v6full1_freeze.json').read_text())
    step=freeze['actions'][0]
    for warm in [True,False]:
        rid=step['run_id']+('-warm' if warm else '')
        setup=json.loads(Path(f'results/v3/{rid}.setup.json').read_text())
        summary=json.loads(Path(f'results/v3/raw/{rid}.summary.json').read_text())
        entry=json.loads(Path(f'results/v3/{rid}.v6_entrypoint.json').read_text())
        args=(dict(step,run_id=rid),setup,summary,entry,parent,seal,freeze,warm)
        with pytest.raises(AssertionError):original(*args)
        before=copy.deepcopy(setup);revision.audit_configuration(*args);assert setup==before
        for flag,bad in [('--max-num-seqs','4'),('--max-num-batched-tokens','4096'),('--kv-cache-memory-bytes','1')]:
            changed=copy.deepcopy(args);changed[1]['actual_engine_argv_list'].extend([flag,bad])
            with pytest.raises(AssertionError):revision.audit_configuration(*changed)


def fixture_registration(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);Path('results/v3').mkdir(parents=True)
    run=revision.FIRST;marker=Path('results/v3')/(run+'.invalid');marker.write_text('Retained audit error')
    freeze=Path('results/v3/v6full1_freeze.json');freeze.write_text('{}')
    interruption=Path('results/v3/v6full1_interruption.json')
    interruption.write_text(json.dumps(dict(phase='audit',completed_arms=0,last_step=dict(run_id=run))))
    raw=Path('raw');raw.write_text('original request bytes')
    r=dict(kind='analysis_only_duplicate_scalar_cli_correction',retained_run_id=run,
        reference_freeze_sha256=sha(freeze),source_sha256={},retained_metadata_sha256={str(p):sha(p) for p in [marker,interruption]},retained_raw_sha256={str(raw):sha(raw)})
    revision.REGISTRATION.write_text(json.dumps(r));return r,raw,interruption


def test_only_registered_audit_interruption_allowed(tmp_path,monkeypatch):
    r,raw,interruption=fixture_registration(tmp_path,monkeypatch)
    revision.validate_retained_audit_interruption(revision.FIRST)
    raw.write_text('changed requests')
    with pytest.raises(AssertionError):revision.validate_retained_audit_interruption(revision.FIRST)


def test_measured_failure_cannot_be_reclassified(tmp_path,monkeypatch):
    r,raw,interruption=fixture_registration(tmp_path,monkeypatch)
    data=json.loads(interruption.read_text());data['phase']='measured';interruption.write_text(json.dumps(data))
    r['retained_metadata_sha256'][str(interruption)]=sha(interruption);revision.REGISTRATION.write_text(json.dumps(r))
    with pytest.raises(AssertionError):revision.validate_retained_audit_interruption(revision.FIRST)


def test_load_revision_changes_only_marker_guard():
    original_text=Path('scripts/v3_analyze_runs.py').read_text()
    expected=original_text.replace("    if (base/f'{run_id}.invalid').exists(): raise ValueError('invalid marker')",'    validate_retained_audit_interruption(run_id)',1)
    expected=expected.replace('import argparse\n','from v6_full_analysis_r1 import validate_retained_audit_interruption\nimport argparse\n',1)
    assert Path('scripts/v6_full_load_r1.py').read_text()==expected
