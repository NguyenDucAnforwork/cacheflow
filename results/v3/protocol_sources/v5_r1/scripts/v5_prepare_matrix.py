"""Prepare consistent-prompt traces and fixed abstention stratum; never overwrite."""
import gzip
import json
import random
import subprocess
import sys
from dataclasses import asdict,replace
from pathlib import Path
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace


def transform(source,target):
    if not target.exists():subprocess.run([sys.executable,'scripts/v5_prepare_trace.py',str(source),'--output',str(target)],check=True)
    m=json.loads(target.with_suffix('.manifest.json').read_text())
    assert m['prompt_version']=='locomo-qwen-concise-v5'


def main():
    root=Path('data/processed/v3')
    for family,qpses in [('dev4b3',[4,2]),('lowreuse8',[4])]:
        for qps in qpses:
            for seed in [101,102,103]:
                transform(root/f'v4-{family}-qps{qps}-s{seed}.jsonl',root/f'v5-{family}-qps{qps}-s{seed}.jsonl')
    for qps in [4,2]:
        for seed in [701,702,703]:
            transform(root/f'v4c1-confirm4b-qps{qps}-s{seed}.jsonl.gz',root/f'v5-confirm4b-qps{qps}-s{seed}.jsonl.gz')
    full=root/'v5-full4b-qps4-s901.jsonl.gz'
    assert full.exists(),'finish the separately running full CPU preparation first'
    rows=load_trace(full);base=json.loads(full.with_suffix('.manifest.json').read_text())
    assert len(rows)==1986 and trace_digest(rows)==base['trace_sha256']
    for seed in [902,903]:
        target=root/f'v5-full4b-qps4-s{seed}.jsonl.gz'
        if not target.exists():subprocess.run([sys.executable,'scripts/v4_retime_trace.py',str(full),
            '--qps','4','--seed',str(seed),'--output',str(target)],check=True)
        m=json.loads(target.with_suffix('.manifest.json').read_text())
        Path(f'results/v3/trace_{target.name.removesuffix(".jsonl.gz")}.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    selected=[]
    for sample in ['conv-26','conv-30','conv-41']:
        selected.extend(sorted([r for r in rows if r.sample_id==sample and r.category==5],key=lambda r:r.qa_index)[:4])
    assert len(selected)==12
    selected.sort(key=lambda r:(r.qa_index,r.sample_id))
    for seed in [101,102,103]:
        target=root/f'v5-abstention12-qps4-s{seed}.jsonl'
        if target.exists():continue
        rng=random.Random(seed);now=0;new=[]
        for row in selected:
            now+=rng.expovariate(4)*1000;new.append(replace(row,offset_ms=round(now)))
        m=dict(base,requests=12,qps=4,seed=seed,selected_samples=['conv-26','conv-30','conv-41'],trace_sha256=trace_digest(new),
            selection='First4 original category5 QA by source index per dev conversation; fixed before V5 GPU evaluation; category/answer not visible to admission')
        target.write_text(''.join(json.dumps(asdict(r),sort_keys=True)+'\n' for r in new))
        target.with_suffix('.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
        Path(f'results/v3/trace_{target.stem}.manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    print('Prepared V5 dev/control/abstention, protocol-repair repeats and three full traces',flush=True)


if __name__=='__main__':main()
