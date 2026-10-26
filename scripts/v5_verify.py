"""Verify unchanged method seal plus prospective consistent-prompt repair seal."""
import hashlib
import json
from pathlib import Path
from v5_method_proof import verify_method as verify_parent


def verify():
    parent,digest=verify_parent();raw=Path('results/v3/v5_prompt_freeze.json').read_bytes();seal=json.loads(raw)
    assert seal['parent_method_freeze_sha256']==digest
    for name,expected in seal['source_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
    for name,expected in seal['input_manifest_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
    assert hashlib.sha256(Path('docs/V5_PROMPT_REPAIR_PLAN.md').read_bytes()).hexdigest()==seal['plan_sha256']
    return parent,seal


if __name__=='__main__':
    parent,seal=verify();print('Verified unchanged V4 method and V5 prompt repair',seal['frozen_utc'])
