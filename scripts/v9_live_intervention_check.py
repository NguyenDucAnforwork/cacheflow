"""Bind a passive nonprogress observation to actual idempotent startup proof."""
import argparse
import json
import time
from pathlib import Path
from v6_raw_archive import sha
from v9_native_identity import identity
from v9_repair_r1 import REG,verify


def check(observation_path,output):
    observation_path=Path(observation_path);output=Path(output);assert not output.exists()
    observation=json.loads(observation_path.read_text());registration=json.loads(REG.read_text());verify(registration)
    assert observation['registration_sha256']==sha(REG) and not observation['terminal_client_result']
    rid=observation['run_id'];step=next(s for s in registration['actions'] if s['run_id']==rid)
    assert step['mode']=='idempotent' and step['probe'] is False
    assert observation['longest_sampled_no_progress']['span_s']>=120
    setup_path=Path('results/v3')/(rid+'.diagnostic_setup.json');setup=json.loads(setup_path.read_text())
    assert observation['setup_sha256']==sha(setup_path) and setup['step']==step
    actual=identity(step,setup['engine'],registration)
    assert actual['engine_pid']==observation['live_processes']['engine']['pid']
    assert actual['engine_birth']==observation['live_processes']['engine']['create_time']
    for name,digest in actual['proof_sha256'].items():assert sha(name)==digest
    result=dict(kind='passive_nonprogress_under_actual_idempotent_native_startup_identity',
        run_id=rid,checked_monotonic_ns=time.monotonic_ns(),observer_source_sha256=sha(__file__),
        observation_path=str(observation_path),observation_sha256=sha(observation_path),registration_sha256=sha(REG),
        native_identity=actual,sampled_nonprogress_s=observation['longest_sampled_no_progress']['span_s'],
        terminal_failure=False,performance_valid=False,research_complete=False,
        scope='Actual idempotent constructor/effective-code fingerprints and PID/birth continuity coexist with sampled nonprogress. The one-site bookkeeping correction is insufficient to rule out this bounded stall. No per-call revalidation, native-state observation, eventual terminal failure, deadlock cause or performance claim.')
    with output.open('x') as out:out.write(json.dumps(result,indent=2)+'\n')
    print('Verified actual idempotent startup identity during sampled nonprogress; no terminal claim',flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('observation',type=Path);p.add_argument('output',type=Path);a=p.parse_args();check(a.observation,a.output)
