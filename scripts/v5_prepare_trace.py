"""Repair both abstention instructions, preserving V4 content/QA/arrival schedule."""
import argparse
import gzip
import hashlib
import json
from dataclasses import asdict,replace
from pathlib import Path
from transformers import AutoTokenizer
from cacheflow.locomo import load_locomo,context_prefix,question_prompt,trace_digest
from cacheflow.v2_replay import load_trace
from cacheflow.v5_prompt import SYSTEM,render
from v5_method_proof import verify_method as verify


def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    freeze,digest=verify();assert not a.output.exists(),'refuse overwrite'
    old=load_trace(a.source);manifest=json.loads(a.source.with_suffix('.manifest.json').read_text())
    assert manifest['prompt_version']=='locomo-qwen-concise-v4' and trace_digest(old)==manifest['trace_sha256']
    from v3_model import get_model
    model=get_model('qwen3-4b');tok=AutoTokenizer.from_pretrained(model['path'],local_files_only=True)
    conversations={c.sample_id:c for c in load_locomo('data/raw/locomo10.json')};new=[];deltas=[]
    for row in old:
        c=conversations[row.sample_id];q=c.questions[row.qa_index]
        expected=tok.apply_chat_template([{'role':'system','content':SYSTEM},
            {'role':'user','content':question_prompt(context_prefix(c),q)}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
        assert expected==row.prompt,'source must be exact V4 rendering, not arbitrary prompt text'
        text=render(tok,c,q);ids=tok.encode(text,add_special_tokens=False)
        assert len(ids)+row.max_tokens<=32768
        deltas.append(len(ids)-row.input_tokens)
        new.append(replace(row,prompt=text,input_tokens=len(ids)))
    result=dict(manifest,prompt_version='locomo-qwen-concise-v5',abstention_style='official_consistent_system_and_user',
        system_instruction=SYSTEM,trace_sha256=trace_digest(new),parent_v4_trace_sha256=manifest['trace_sha256'],
        parent_method_freeze_sha256=digest,prompt_repair='Only canonical user instruction footer changes; conversation/QA/order/offset/output budget unchanged',
        renderer_sha256=hashlib.sha256(Path('src/cacheflow/v5_prompt.py').read_bytes()).hexdigest(),
        input_token_delta_min=min(deltas),input_token_delta_max=max(deltas))
    result.pop('method_freeze_sha256',None)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    opener=gzip.open if a.output.suffix=='.gz' else open
    with opener(a.output,'wt',encoding='utf-8') as f:
        for row in new:f.write(json.dumps(asdict(row),sort_keys=True)+'\n')
    a.output.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    name=a.output.name.removesuffix('.jsonl.gz').removesuffix('.jsonl')
    Path(f'results/v3/trace_{name}.manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print('Verified V5 trace',name,len(new),'token delta',min(deltas),max(deltas),flush=True)


if __name__=='__main__':main()
