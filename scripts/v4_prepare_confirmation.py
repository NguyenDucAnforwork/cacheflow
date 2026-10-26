"""Derive fresh arrival traces from verified exact V4 prompts after method freeze."""
import gzip
import json
import random
import argparse
from dataclasses import asdict,replace
from pathlib import Path
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace
from v4_verify_freeze import verify

p=argparse.ArgumentParser();p.add_argument('--prefix',default='v4c1-confirm4b');args=p.parse_args()
assert args.prefix.replace('-','').isalnum()
freeze,freeze_sha=verify()
source=Path('data/processed/v3/v4-full4b-qps4-s901.jsonl.gz')
manifest=json.loads(source.with_suffix('.manifest.json').read_text())
rows=load_trace(source);assert len(rows)==1986 and trace_digest(rows)==manifest['trace_sha256']
assert manifest['trace_sha256']==freeze['parent_full_trace_sha256']
assert manifest['model_revision']==freeze['model_revision'] and manifest['prompt_version']==freeze['prompt_version']
selected=[r for r in rows if r.sample_id in {'conv-43','conv-44'} and r.qa_index<20]
assert len(selected)==len({r.request_id for r in selected})==40
assert {r.qa_index for r in selected if r.sample_id=='conv-43'}==set(range(20))
assert {r.qa_index for r in selected if r.sample_id=='conv-44'}==set(range(20))
for qps in [4,2]:
    for seed in [701,702,703]:
        rng=random.Random(seed);now=0;new=[]
        for row in selected:
            now+=rng.expovariate(qps)*1000;new.append(replace(row,offset_ms=round(now)))
        target=Path(f'data/processed/v3/{args.prefix}-qps{qps}-s{seed}.jsonl.gz')
        assert not target.exists(),'refusing overwrite'
        with gzip.open(target,'wt',encoding='utf-8') as file:
            for row in new:file.write(json.dumps(asdict(row),sort_keys=True)+'\n')
        m=manifest|dict(requests=40,selected_samples=['conv-43','conv-44'],qps=qps,seed=seed,
            trace_sha256=trace_digest(new),parent_trace_sha256=manifest['trace_sha256'],
            method_freeze_sha256=freeze_sha,scope='Prospective conversation-disjoint V4 confirmation; CPU preparation only')
        target.with_suffix('.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
        Path(f'results/v3/trace_{args.prefix.replace("-","_")}_qps{qps}_s{seed}.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
        print('Prepared',target.name,m['trace_sha256'])
