"""Explicit analysis-only revision for duplicated scalar CLI options.

The original seal, sources, raw ledgers and audit-interruption marker stay intact.
Only the single registered audit-stage marker may be analyzed by this revision.
"""
import copy
import json
from pathlib import Path
from v6_raw_archive import sha

REGISTRATION=Path('results/v3/v6full1_analysis_r1_registration.json')
FIRST='v6full1-main-g6-fifo64-s901'


def scalar_argv(argv, flags):
    """Canonicalize argparse store options: the last explicit value wins."""
    found={};keep=[];i=0
    while i<len(argv):
        token=argv[i];key=token.split('=',1)[0]
        if key in flags:
            if '=' in token:value=token.split('=',1)[1]
            else:
                assert i+1<len(argv) and not argv[i+1].startswith('--'),key
                i+=1;value=argv[i]
            assert value and value.lstrip('+-').isdigit(),(key,value)
            found[key]=value
        else:keep.append(token)
        i+=1
    assert set(found)==set(flags),('Missing scalar CLI option',set(flags)-found.keys())
    return keep+[item for key,value in found.items() for item in [key,value]]


def audit_configuration(*args,**kwargs):
    from v6_full_contracts import audit_configuration as original
    step,setup,*rest=args
    setup=copy.deepcopy(setup)
    if step['engine']=='main':
        setup['actual_engine_argv_list']=scalar_argv(setup['actual_engine_argv_list'],
            {'--max-num-seqs','--max-num-batched-tokens','--kv-cache-memory-bytes'})
    return original(step,setup,*rest,**kwargs)


def verify_revision():
    r=json.loads(REGISTRATION.read_text())
    assert r['kind']=='analysis_only_duplicate_scalar_cli_correction'
    for name,digest in r['source_sha256'].items():assert sha(name)==digest,name
    for name,digest in r['retained_metadata_sha256'].items():assert sha(name)==digest,name
    assert sha('results/v3/v6full1_freeze.json')==r['reference_freeze_sha256']
    return r


def validate_retained_audit_interruption(run_id):
    marker=Path('results/v3')/(run_id+'.invalid')
    if not marker.exists():return
    r=verify_revision();assert run_id==FIRST and r['retained_run_id']==run_id
    interruption=json.loads(Path('results/v3/v6full1_interruption.json').read_text())
    assert interruption['phase']=='audit' and interruption['completed_arms']==0
    assert interruption['last_step']['run_id']==run_id
    # The initial bytes are checked even after verified lossless archival.
    from v6_raw_archive import uncompressed_sha
    for name,digest in r['retained_raw_sha256'].items():
        path=Path(name)
        assert (sha(path) if path.exists() else uncompressed_sha(str(path)+'.gz'))==digest,name
