"""Projected proof rejection tests; no full regeneration or namespace execution."""
import copy
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path('scripts').resolve()))
from v6_after_input_reproduction import validate_input_result


def fixture():
    freeze=json.loads(Path('results/v3/v6full1_freeze.json').read_text())
    paths=sorted({s['trace'] for s in freeze['actions']})
    proof=dict(complete=True,cpu_only=True,registration_sha256='registered',unique_qa=1986,answerable=1540,category5=446,input_tokens=50522325,
        prompt_and_token_fingerprints_equal=True,original_inputs_unchanged=True,
        seeds=[dict(original_path=p,seed=seed,requests=1986,generated_from_official_source=True,
            original_stored_sha256=freeze['input_file_sha256'][p],restored_identity=dict(stored_sha256=freeze['input_file_sha256'][p])) for p,seed in zip(paths,[901,902,903])])
    return proof,freeze


def test_complete_actual_scope_is_required_including_all_three_stored_hashes():
    proof,freeze=fixture();validate_input_result(proof,'registered',freeze)
    for mutate in [lambda p:p.update(complete=False),lambda p:p.update(cpu_only=False),lambda p:p.update(unique_qa=60),
                   lambda p:p.update(registration_sha256='different'),lambda p:p.update(prompt_and_token_fingerprints_equal=False),
                   lambda p:p.update(original_inputs_unchanged=False),lambda p:p['seeds'].pop(),
                   lambda p:p['seeds'][0].update(generated_from_official_source=False),lambda p:p['seeds'][0]['restored_identity'].update(stored_sha256='different')]:
        changed=copy.deepcopy(proof);mutate(changed)
        with pytest.raises(AssertionError):validate_input_result(changed,'registered',freeze)


def test_seed_labels_cannot_be_permuted_while_retaining_the_same_seed_set():
    proof,freeze=fixture();proof['seeds'][1]['seed'],proof['seeds'][2]['seed']=proof['seeds'][2]['seed'],proof['seeds'][1]['seed']
    with pytest.raises(AssertionError):validate_input_result(proof,'registered',freeze)
