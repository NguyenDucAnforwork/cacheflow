"""Freeze concise chat QA traces without answers/evidence in prompts."""
import argparse
import gzip
import json
from dataclasses import asdict, replace
from pathlib import Path

from transformers import AutoTokenizer
from cacheflow.locomo import build_trace, load_locomo, source_sha256, trace_digest

p=argparse.ArgumentParser()
p.add_argument('--samples',nargs='+',default=['conv-26','conv-30','conv-41'])
p.add_argument('--questions',type=int,default=20)
p.add_argument('--seed',type=int,default=101)
p.add_argument('--qps',type=float,default=1)
p.add_argument('--arrival',choices=['interleaved','grouped','low_reuse'],default='interleaved')
p.add_argument('--output',type=Path,required=True)
p.add_argument('--model-path',default='/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e')
p.add_argument('--abstention-style',choices=['legacy','official'],default='legacy')
args=p.parse_args()
model=args.model_path
tok=AutoTokenizer.from_pretrained(model,local_files_only=True)
source=Path('data/raw/locomo10.json')
rows,manifest=build_trace(load_locomo(source),tok,sample_ids=tuple(args.samples),
    max_questions_per_sample=args.questions,max_model_len=32768,output_tokens=96,
    qps=args.qps,seed=args.seed,arrival=args.arrival)
system=('Answer the question using only the supplied conversation. Return only a concise answer, '
        'without explanation, reasoning, repetition, or restating the question. '
        'If the answer is not present in the conversation, answer "I don\'t know".')
if args.abstention_style=='official':
    system=system.replace('"I don\'t know"','"No information available."')
wrapped=[]
for row in rows:
    text=tok.apply_chat_template([{'role':'system','content':system},
        {'role':'user','content':row.prompt}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
    ids=tok.encode(text,add_special_tokens=False)
    assert len(ids)+row.max_tokens<=32768
    assert text.count(row.prompt)==1
    wrapped.append(replace(row,prompt=text,input_tokens=len(ids)))
manifest.update(source_sha256=source_sha256(source),prompt_version='locomo-qwen-concise-v4' if args.abstention_style=='official' else 'locomo-qwen-concise-v3',
    abstention_style=args.abstention_style,
    system_instruction=system,thinking=False,model_revision=Path(model).name,trace_sha256=trace_digest(wrapped))
args.output.parent.mkdir(parents=True,exist_ok=True)
if args.output.exists():
    raise ValueError('refusing to overwrite a frozen trace')
text=''.join(json.dumps(asdict(r),sort_keys=True)+'\n' for r in wrapped)
if args.output.suffix=='.gz':
    with gzip.open(args.output,'wt',encoding='utf-8') as file:file.write(text)
else:args.output.write_text(text)
args.output.with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
print(json.dumps(manifest,sort_keys=True))
