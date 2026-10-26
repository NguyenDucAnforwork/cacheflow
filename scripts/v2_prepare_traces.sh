#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
venv=${CACHEFLOW_VENV:-/venv/main}
model=${CACHEFLOW_MODEL_PATH:-/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e}
cd "$root"
[[ -f data/raw/locomo10.json ]] || { echo "LoCoMo source missing" >&2; exit 1; }
[[ -f "$model/tokenizer.json" ]] || { echo "pinned tokenizer missing" >&2; exit 1; }
echo '79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4  data/raw/locomo10.json' | sha256sum -c -
mkdir -p data/processed/v2
export PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}"
python="$venv/bin/python"
"$python" scripts/v2_prefix_probe.py \
    --tokenizer-path "$model" --output data/processed/v2/e1_2k_50ms_1pair.jsonl \
    --prefix-tokens 2048 --pairs 1 --follower-offset-ms 50 --seed 7
"$python" scripts/v2_locomo.py trace \
    --source data/raw/locomo10.json --tokenizer-path "$model" \
    --output data/processed/v2/locomo_b1_fullctx_1qa.jsonl \
    --protocol p_qa --arrival interleaved --sample-ids conv-26 \
    --max-model-len 32768 --max-questions-per-sample 1 \
    --output-tokens 64 --seed 7
"$python" scripts/v2_locomo.py trace \
    --source data/raw/locomo10.json --tokenizer-path "$model" \
    --output data/processed/v2/locomo_dev_2conv_interleaved.jsonl \
    --protocol p_qa --arrival interleaved --sample-ids conv-26 conv-30 \
    --max-model-len 32768 --max-questions-per-sample 15 \
    --output-tokens 64 --seed 7
"$python" scripts/v2_locomo.py trace \
    --source data/raw/locomo10.json --tokenizer-path "$model" \
    --output data/processed/v2/locomo_dev_2conv_session.jsonl \
    --protocol p_session --arrival interleaved --sample-ids conv-26 conv-30 \
    --max-model-len 32768 --max-questions-per-sample 15 \
    --output-tokens 64 --seed 7 --session-gap-ms 1000
"$python" - <<'PY_CHECK'
import json
from pathlib import Path
from cacheflow.locomo import trace_digest
from cacheflow.v2_replay import load_trace
expected = {
    'e1_2k_50ms_1pair': (2, 'a2e44487457bf1378c0ea6f955588add37208d199f0f939b484de12e502fbc16'),
    'locomo_b1_fullctx_1qa': (1, '1559381e885668d7430a3cf21bc11748ba4e325c2a1805ae9406c7315042c44c'),
    'locomo_dev_2conv_interleaved': (30, '5acdf79bcaf5bf9a307f732d2ffb97256d41b13c210ef761be5986e44189bd9a'),
    'locomo_dev_2conv_session': (30, 'fdeb1efd65c992c2fc33f7b7b583e067ca359f85d9858f802db48752d1038209'),
}
for name, (count, digest) in expected.items():
    path = Path('data/processed/v2') / f'{name}.jsonl'
    rows = load_trace(path)
    manifest = json.loads(path.with_suffix('.manifest.json').read_text())
    if len(rows) != count or trace_digest(rows) != digest or manifest['trace_sha256'] != digest:
        raise SystemExit(f'trace mismatch: {name}')
    print(name, count, digest)
PY_CHECK
