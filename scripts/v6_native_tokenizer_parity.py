"""CPU-only parity with the native tokenizer loader and batching call path."""
import hashlib
import importlib.metadata
import inspect
import json
import struct
from pathlib import Path
from sglang.srt.utils.hf_transformers.tokenizer import get_tokenizer
import sglang


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    oraclepath=Path('results/v3/v6dev1_input_oracle.json');oracle=json.loads(oraclepath.read_text())
    model=Path('/workspace/.hf_home/hub/models--Qwen--Qwen3-4B/snapshots')/oracle['model_revision']
    tokenizer=get_tokenizer(str(model),tokenizer_mode='auto',tokenizer_backend='huggingface',trust_remote_code=False,local_files_only=True)
    trace=Path('data/processed/v3/v5-dev4b3-qps4-s101.jsonl');assert sha(trace)==oracle['trace_sha256']
    rows=[json.loads(l) for l in trace.read_text().splitlines()];expected={r['request_id']:r for r in oracle['requests']};results=[]
    for row in rows:
        # Native tokenizer_manager fast single-string path uses a batch call
        # with default special-token behavior, not this project's gateway encoder.
        ids=tokenizer([row['prompt']])['input_ids'][0];digest=hashlib.sha256(struct.pack('<'+'I'*len(ids),*ids)).hexdigest()
        ref=expected[row['request_id']];assert len(ids)==row['input_tokens']==ref['input_tokens'] and digest==ref['token_ids_u32le_sha256']
        results.append(dict(request_id=row['request_id'],input_tokens=len(ids),token_ids_u32le_sha256=digest))
    native_root=Path(sglang.__file__).parent
    sources=[Path(inspect.getsourcefile(get_tokenizer)),native_root/'srt/managers/tokenizer_manager.py']
    result=dict(cpu_only=True,requests=len(results),token_id_mismatches=0,input_oracle_sha256=sha(oraclepath),
        trace_sha256=sha(trace),model_revision=oracle['model_revision'],native_tokenizer_class=type(tokenizer).__name__,
        package_versions={n:importlib.metadata.version(n) for n in ['sglang','transformers','tokenizers']},
        native_source_sha256={str(p):sha(p) for p in sources},source_sha256=sha(__file__),token_fingerprints=results,
        scope='CPU native get_tokenizer auto/huggingface loader, default fast batched call matching the inspected tokenizer_manager path; compare every token ID against main-environment oracle encoding. No GPU execution, server request trace, runtime cache correctness or latency claim.')
    Path('results/v3/sglang/v6dev1_native_tokenizer_parity.json').write_text(json.dumps(result,indent=2)+'\n')
    print('CPU native tokenizer parity',len(results),'prompts,0token-ID mismatches; no GPU execution')


if __name__=='__main__':main()
