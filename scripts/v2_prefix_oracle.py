"""Static no-eviction prefix-sharing opportunity at different block granularities.

This is a token-content oracle, not an execution simulator. It assumes every
prior prompt is fully materialized before the next one and omits output tokens.
"""
import argparse
import json
from pathlib import Path

from transformers import AutoTokenizer

from cacheflow.v2_replay import load_trace
from cacheflow.locomo import trace_digest

p = argparse.ArgumentParser()
p.add_argument('--trace', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--tokenizer-path', default='/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e')
args = p.parse_args()
tok = AutoTokenizer.from_pretrained(args.tokenizer_path, local_files_only=True)
rows = load_trace(args.trace)
previous = []
result = []
for row in rows:
    ids = tok.encode(row.prompt, add_special_tokens=False)
    if len(ids) != row.input_tokens:
        raise ValueError('tokenizer count mismatch')
    common = 0
    for prior in previous:
        lcp = next((i for i, (a, b) in enumerate(zip(ids, prior)) if a != b), min(len(ids), len(prior)))
        common = max(common, min(lcp, len(ids)-1))
    result.append(dict(request_id=row.request_id, input_tokens=len(ids), common_prefix_tokens=common,
                       cached_block16=common//16*16, cached_chunk256=common//256*256))
    previous.append(ids)
total = sum(r.input_tokens for r in rows)
args.output.write_text(json.dumps(dict(trace_sha256=trace_digest(rows), requests=len(rows), input_tokens=total,
    assumption='Static no eviction; prior prompts fully materialized; no generated text; not a runtime simulation.',
    cached_block16=sum(r['cached_block16'] for r in result),
    cached_chunk256=sum(r['cached_chunk256'] for r in result),
    prefill_block16=total-sum(r['cached_block16'] for r in result),
    prefill_chunk256=total-sum(r['cached_chunk256'] for r in result),
    per_request=result),indent=2)+'\n')
print(args.output)
