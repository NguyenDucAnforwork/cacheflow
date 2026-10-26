"""Regenerate frozen E2/confirmation traces; reject divergent existing content."""
import json
from dataclasses import asdict
from pathlib import Path

from transformers import AutoTokenizer

from cacheflow.locomo import build_trace, load_locomo, source_sha256
from cacheflow.v2_replay import load_trace
from cacheflow.locomo import trace_digest

root = Path(__file__).resolve().parents[1]
model = Path('/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e')
tokenizer = AutoTokenizer.from_pretrained(model, local_files_only=True)
source = root / 'data/raw/locomo10.json'
conversations = load_locomo(source)
known = json.loads((root / 'results/v2/e2_trace_manifests.json').read_text())
for cohort, ids, limit, seeds in [('dev3', ('conv-26','conv-30','conv-41'), 10, [17,29,43]),
                                  ('holdout2', ('conv-49','conv-50'), 15, [101,211,307])]:
    for seed in seeds:
        path = root / f'data/processed/v2/e2_{cohort}_qps02_s{seed}.jsonl'
        rows, manifest = build_trace(conversations, tokenizer, sample_ids=ids,
                                     max_model_len=32768, max_questions_per_sample=limit,
                                     qps=.2, seed=seed)
        manifest['source_sha256'] = source_sha256(source)
        expected = known[path.with_suffix('.manifest.json').stem]['trace_sha256']
        if manifest['trace_sha256'] != expected:
            raise ValueError(f'regenerated trace diverged: {path}')
        if path.exists() and trace_digest(load_trace(path)) != expected:
            raise ValueError(f'existing trace diverged: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(''.join(json.dumps(asdict(r), sort_keys=True)+'\n' for r in rows))
        manifest_path = path.with_suffix('.manifest.json')
        if manifest_path.exists():
            if json.loads(manifest_path.read_text()) != manifest:
                raise ValueError(f'existing manifest diverged: {manifest_path}')
        else:
            manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
        print('VERIFIED', path.name, expected)
