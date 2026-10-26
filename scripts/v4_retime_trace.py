"""Freeze new arrival schedules over exact existing prompts without retokenization."""
import argparse
import gzip
import json
import random
from dataclasses import asdict,replace
from pathlib import Path
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace

p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True)
p.add_argument('--qps',type=float,required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args()
assert not a.output.exists() and a.qps>0
rows=load_trace(a.source);manifest=json.loads(a.source.with_suffix('.manifest.json').read_text())
assert trace_digest(rows)==manifest['trace_sha256']
rng=random.Random(a.seed);now=0;new=[]
for row in rows:
    now+=rng.expovariate(a.qps)*1000
    new.append(replace(row,offset_ms=round(now)))
manifest.update(qps=a.qps,seed=a.seed,trace_sha256=trace_digest(new),
    retimed_from_trace_sha256=trace_digest(rows),retiming='Same random.expovariate arrival generator; prompt/order unchanged')
a.output.parent.mkdir(parents=True,exist_ok=True)
text=''.join(json.dumps(asdict(r),sort_keys=True)+'\n' for r in new)
if a.output.suffix=='.gz':
    with gzip.open(a.output,'wt',encoding='utf-8') as file:file.write(text)
else:a.output.write_text(text)
a.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest,sort_keys=True))
