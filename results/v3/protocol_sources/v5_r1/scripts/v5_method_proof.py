"""Prove V4 admission sources unchanged, allowing only explicit timeout knobs.

Historical source is recovered from the committed V4 checkpoint and SHA-checked
against its original seal. No scheduler, hashing, tokenizer or KV logic changes.
"""
import hashlib
import json
import subprocess
from pathlib import Path

PATCHES={
 'src/cacheflow/gateway.py':[(
  'httpx.Timeout(connect=30, read=600, write=30, pool=30)',
  'httpx.Timeout(connect=30, read=float(settings.get("http_read_timeout_s",600)), write=30, pool=30)'),
  ("'completed_history_requests': len(scheduler._recent),","'completed_history_requests': len(scheduler._recent),\n                'upstream_read_timeout_s': client.timeout.read,")],
 'src/cacheflow/v2_replay.py':[
  ('import json\n','import json\nimport os\n'),
  ('httpx.Timeout(connect=30, read=600, write=30, pool=600)',
   'httpx.Timeout(connect=30, read=float(os.environ.get("CACHEFLOW_REQUEST_READ_TIMEOUT_S",600)), write=30, pool=float(os.environ.get("CACHEFLOW_REQUEST_POOL_TIMEOUT_S",600)))'),
  ('"run_id": args.run_id, "git_sha": git_sha, "trace_sha256": trace_sha,',
   '"run_id": args.run_id, "git_sha": git_sha, "trace_sha256": trace_sha,\n        "request_read_timeout_s": timeout.read, "request_pool_timeout_s": timeout.pool,')]
}
REFERENCE='a6c118c'


def verify_method():
    raw=Path('results/v3/v4_method_freeze.json').read_bytes();parent=json.loads(raw)
    current=dict(parent['source_sha256'])
    for name,expected in parent['source_sha256'].items():
        actual=Path(name).read_bytes()
        if name in PATCHES:
            old=subprocess.check_output(['git','show',f'{REFERENCE}:{name}'])
            assert hashlib.sha256(old).hexdigest()==expected,'reference differs from V4 seal'
            projected=old.decode()
            for before,after in PATCHES[name]:
                assert projected.count(before)==1,(name,before)
                projected=projected.replace(before,after,1)
            assert actual==projected.encode(),('unapproved non-timeout change',name)
        else:assert hashlib.sha256(actual).hexdigest()==expected,name
        current[name]=hashlib.sha256(actual).hexdigest()
    for name,expected in parent['input_manifest_sha256'].items():assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected,name
    assert hashlib.sha256(Path('docs/V4_CONFIRMATION_PLAN.md').read_bytes()).hexdigest()==parent['plan_sha256']
    return dict(parent,source_sha256=current),hashlib.sha256(raw).hexdigest()
