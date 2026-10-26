"""Prepare two extra full arrival schedules without changing frozen prompts."""
import json
import subprocess
import sys
from pathlib import Path
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace
from v4_verify_freeze import verify

freeze,digest=verify()
source=Path('data/processed/v3/v4-full4b-qps4-s901.jsonl.gz')
assert trace_digest(load_trace(source))==freeze['parent_full_trace_sha256']
for seed in [902,903]:
    target=Path(f'data/processed/v3/v4c1-full4b-qps4-s{seed}.jsonl.gz')
    if not target.exists():
        subprocess.run([sys.executable,'scripts/v4_retime_trace.py',str(source),'--qps','4',
            '--seed',str(seed),'--output',str(target)],check=True)
        m=json.loads(target.with_suffix('.manifest.json').read_text());m['method_freeze_sha256']=digest
        target.with_suffix('.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    m=json.loads(target.with_suffix('.manifest.json').read_text())
    rows=load_trace(target)
    assert len(rows)==1986 and trace_digest(rows)==m['trace_sha256'] and m['method_freeze_sha256']==digest
    Path(f'results/v3/trace_v4c1_full4b_qps4_s{seed}.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print('Verified full trace',seed,m['trace_sha256'])
