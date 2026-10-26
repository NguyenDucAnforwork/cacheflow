"""CPU-only streamed tokenizer fingerprints; never initializes an inference model."""
import argparse
import gzip
import hashlib
import importlib.metadata
import inspect
import json
import struct
from pathlib import Path
from v3_model import get_model
from v6_input_oracle import minimum_work
from v6_trace_hashes import CanonicalTraceDigest


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=['main','native'],required=True);p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args()
    assert not a.output.exists() and (a.limit is None or a.limit>0)
    model=get_model('qwen3-4b');root=Path(model['path']);sources={};packages=['transformers','tokenizers']
    if a.backend=='main':
        from transformers import AutoTokenizer
        tokenizer=AutoTokenizer.from_pretrained(root,local_files_only=True)
    else:
        import sglang
        from sglang.srt.utils.hf_transformers.tokenizer import get_tokenizer
        tokenizer=get_tokenizer(str(root),tokenizer_mode='auto',tokenizer_backend='huggingface',trust_remote_code=False,local_files_only=True)
        packages+=['sglang'];nr=Path(sglang.__file__).parent
        sources={str(n):sha(n) for n in [Path(inspect.getsourcefile(get_tokenizer)),nr/'srt/managers/tokenizer_manager.py']}
    rows=[];plain_digest=hashlib.sha256();canonical=CanonicalTraceDigest()
    def sequences():
        opener=gzip.open if a.trace.suffix=='.gz' else open
        with opener(a.trace,'rb') as f:
            for i,line in enumerate(f):
                if a.limit is not None and i>=a.limit:break
                plain_digest.update(line);r=json.loads(line);canonical.update(r)
                ids=tokenizer.encode(r['prompt'],add_special_tokens=False) if a.backend=='main' else tokenizer([r['prompt']])['input_ids'][0]
                assert len(ids)==r['input_tokens'] and len(ids)+r['max_tokens']<=32768 and r['max_tokens']==96
                rows.append(dict(request_id=r['request_id'],sample_id=r['sample_id'],qa_index=r['qa_index'],input_tokens=len(ids),max_tokens=r['max_tokens'],
                    prompt_sha256=hashlib.sha256(r['prompt'].encode()).hexdigest(),token_ids_u32le_sha256=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()))
                yield ids
    oracle=minimum_work(sequences(),16);manifest=json.loads(a.trace.with_suffix('.manifest.json').read_text())
    if a.limit is None:
        assert oracle['requests']==manifest['requests'] and canonical.hexdigest()==manifest['trace_sha256']
    result=dict(cpu_only=True,complete_trace=a.limit is None,backend=a.backend,model_revision=model['revision'],tokenizer_class=type(tokenizer).__name__,
        trace_path=str(a.trace),trace_stored_sha256=sha(a.trace),trace_uncompressed_sha256=plain_digest.hexdigest(),trace_canonical_sha256=canonical.hexdigest(),manifest_sha256=sha(a.trace.with_suffix('.manifest.json')),
        package_versions={n:importlib.metadata.version(n) for n in packages},native_source_sha256=sources,
        tokenizer_artifact_sha256={str(n):sha(n) for n in root.iterdir() if n.is_file() and n.suffix in {'.json','.jinja'}},
        source_sha256=sha(__file__),canonical_implementation_sha256=sha('scripts/v6_trace_hashes.py'),oracle_source_sha256=sha('scripts/v6_input_oracle.py'),page16=oracle,requests=rows,
        scope='CPU input/tokenizer parity and exact input-only full-retention causal-block reference. No model weights loaded, GPU engine, serving performance, runtime publication/eviction/IO simulation, or quality evaluation.')
    with a.output.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(a.backend,'CPU token fingerprints',len(rows),'complete trace',result['complete_trace'],flush=True)


if __name__=='__main__':main()
