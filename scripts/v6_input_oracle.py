"""Exact input-only causal-prefix minimum, not a runtime scheduling simulator.

Each distinct complete block in a prefix trie is computed once with unlimited
retention; every request's partial final block remains private. No generated
answers, measured ordering, cache metrics or future QA labels enter the model.
"""
import hashlib
import json
import struct
from pathlib import Path


def minimum_work(sequences,block_size=16):
    assert isinstance(block_size,int) and block_size>0
    nodes={};total=0;private_tails=0;requests=0
    for ids in sequences:
        assert ids and all(isinstance(t,int) and t>=0 for t in ids)
        requests+=1;total+=len(ids);parent=0;end=len(ids)//block_size*block_size
        for start in range(0,end,block_size):
            key=(parent,tuple(ids[start:start+block_size]))
            if key not in nodes:nodes[key]=len(nodes)+1
            parent=nodes[key]
        private_tails+=len(ids)-end
    assert requests>0
    return dict(requests=requests,input_tokens=total,block_size=block_size,distinct_complete_causal_blocks=len(nodes),
        private_partial_tail_tokens=private_tails,input_only_minimum_new_tokens=len(nodes)*block_size+private_tails)


def main():
    from transformers import AutoTokenizer
    from v3_model import get_model
    model=get_model('qwen3-4b');root=Path(model['path']);tokenizer=AutoTokenizer.from_pretrained(root,local_files_only=True)
    trace=Path('data/processed/v3/v5-dev4b3-qps4-s101.jsonl');data=trace.read_bytes();rows=[json.loads(l) for l in data.splitlines()]
    sequences=[];fingerprints=[]
    for row in rows:
        ids=tokenizer.encode(row['prompt'],add_special_tokens=False);assert len(ids)==row['input_tokens'];sequences.append(ids)
        fingerprints.append(dict(request_id=row['request_id'],sample_id=row['sample_id'],qa_index=row['qa_index'],input_tokens=len(ids),
            token_ids_u32le_sha256=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()))
    page=minimum_work(sequences,16);token=minimum_work(sequences,1)
    assert page==minimum_work(reversed(sequences),16),'Static full-retention block union must be order-independent'
    checkpoint=Path('results/v3/sglang/v6native1_primary_s101_checkpoint_audit.json');observations=[]
    if checkpoint.exists():
        for row in json.loads(checkpoint.read_text())['runs']:
            observations.append(dict(run_id=row['run_id'],observed_new_prefill_tokens=row['computed_tokens'],
                excess_over_input_only_page16_minimum=row['computed_tokens']-page['input_only_minimum_new_tokens']))
    result=dict(scope='Static input-only structural reference on60exposedQA. Exact tuple-prefix trie, no hash collision assumption. Unlimited retention, immediately reusable complete blocks, private partial tails, no generated suffix reuse, no native transient-publication/batching/admission/IO/queue model. Not a simulator, measured native per-request work join, or causal speedup proof.',
        trace_sha256=hashlib.sha256(data).hexdigest(),manifest_sha256=hashlib.sha256(trace.with_suffix('.manifest.json').read_bytes()).hexdigest(),
        model_revision=model['revision'],tokenizer_artifact_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file() and p.suffix in {'.json','.jinja'}},
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),page16=page,token_level=token,requests=fingerprints,
        observed_single_native_block=observations,checkpoint_audit_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint.exists() else None)
    Path('results/v3/v6dev1_input_oracle.json').write_text(json.dumps(result,indent=2)+'\n')
    print('Exact input-only reference',page,flush=True)
    for row in observations:print(row)


if __name__=='__main__':main()
