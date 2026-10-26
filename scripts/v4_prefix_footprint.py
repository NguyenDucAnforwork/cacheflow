"""Static full-trace prefix working set; no GPU or QA answers used."""
import argparse
import hashlib
import json
from pathlib import Path

from transformers import AutoTokenizer
from cacheflow.v2_replay import load_trace
from cacheflow.v3_residency import engine_block_hashes

p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert not a.output.exists(),'refuse overwrite'
rows=load_trace(a.trace)
model='/workspace/.hf_home/hub/models--Qwen--Qwen3-4B/snapshots/1cfa9a7208912126459214e8b04321603b3df60c'
tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
common={};counts={}
for row in rows:
    ids=tokenizer.encode(row.prompt,add_special_tokens=False)
    assert len(ids)==row.input_tokens
    if row.sample_id not in common:common[row.sample_id]=ids
    else:
        previous=common[row.sample_id];length=0
        for x,y in zip(previous,ids):
            if x!=y:break
            length+=1
        common[row.sample_id]=previous[:length]
    counts[row.sample_id]=counts.get(row.sample_id,0)+1
union=set()
for ids in common.values():union.update(engine_block_hashes(ids))
values={k:dict(questions=counts[k],common_prefix_tokens=len(v),cpu_chunk_aligned_tokens=len(v)//256*256)
        for k,v in common.items()}
result=dict(scope='Static common-prefix geometry only; private QA suffixes/outputs are additional and evictable; not runtime residency',
    model_revision=Path(model).name,requests=len(rows),by_conversation=values,
    shared_gpu_block_union_tokens=len(union)*16,
    reusable_cpu_chunk_tokens=sum(v['cpu_chunk_aligned_tokens'] for v in values.values()),
    bytes_per_token=147456)
result['reusable_cpu_KV_GiB']=result['reusable_cpu_chunk_tokens']*147456/1024**3
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
