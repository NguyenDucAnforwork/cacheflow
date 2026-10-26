"""Verify frozen source and input manifests before prospective evaluation."""
import hashlib
import json
from pathlib import Path


def verify():
    path=Path('results/v3/v4_method_freeze.json');raw=path.read_bytes();freeze=json.loads(raw)
    assert freeze['status']=='frozen_prospective_configuration_not_completion'
    for name,expected in freeze['source_sha256'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,('frozen source changed',name)
    for name,expected in freeze.get('input_manifest_sha256',{}).items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,('frozen input manifest changed',name)
    assert hashlib.sha256(Path('docs/V4_CONFIRMATION_PLAN.md').read_bytes()).hexdigest()==freeze['plan_sha256']
    return freeze,hashlib.sha256(raw).hexdigest()


if __name__=='__main__':
    freeze,digest=verify();print('Verified freeze',freeze['frozen_utc'],digest,len(freeze['source_sha256']),'source files')
