# CacheFlow V2: new host and execution log

Status: V2 data audit complete; serving stack installation and 32K memory pilot pending. Work was paused at the owner's request; see `docs/PROGRESS.md` for the exact server handoff. This log is separate from the V1 host log in `docs/reproduce.md`.

## Owner decision (2026-10-25)

The owner explicitly skipped proposal milestone M1 (old-baseline restoration). V2 will not reproduce the old synthetic timing baseline on this host. Historical V1 results remain in `docs/main_results.md` and are not compared causally with new-host measurements. New B1/B2 runs, if any, are matched V2 experimental arms only.

## Host snapshot (2026-10-25, Asia/Bangkok)

| Item | Observed |
| --- | --- |
| SSH alias | `optim`; account `root` |
| GPU | GeForce RTX 3090, 24,576 MiB; 24,126 MiB free at inventory |
| Driver | 595.71.05 |
| CUDA toolkit | 12.8; driver maximum CUDA 13.2 (`vast-capabilities`) |
| RAM | 125 GiB total, 115 GiB available at inventory |
| `/workspace` disk | 25 GiB free on overlay at inventory |
| `/workspace` durability | `workspace_is_volume=false`; sync valuable data to GitHub |
| Python | system 3.12.3, `/venv/main` 3.12.15 |
| Existing PyTorch | 2.11.0+cu128 in `/venv/main` |
| vLLM / LMCache / transformers | absent from `/venv/main` at inventory |
| Tools | Git, uv and supervisor present; `gh` absent |

The Vast instance guide `/etc/vast-agents-guide.md` was read before instance work. This is an unprivileged container, so services should be managed with supervisor. The current `/workspace` contains only image-created files and no CacheFlow clone.

## Repository and source provenance

- Private repo: `NguyenDucAnforwork/cacheflow`.
- V1 branch `feat/cacheflow-6h` at `ef8892e53ff9cb04486707e2844f2535277b9888` when V2 work began.
- New branch: `feat/cacheflow-v2-locomo`. V1 results and original docs are retained.
- LoCoMo source: `snap-research/locomo`, commit `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`.
- Official `data/locomo10.json` SHA256: `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`.
- LoCoMo source license is CC BY-NC 4.0. Raw JSON is excluded from this repository; source URLs and hashes are recorded.
- Model/tokenizer: `Qwen/Qwen3-1.7B`, pinned revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.

## Data schema findings

The official file has 10 conversations and 1,986 QA annotations. The sessions are numbered in chronological order. There are 444 category-5 adversarial QA records without a normal `answer` field; keep them distinct during scoring. A small number of evidence cells combine IDs or contain malformed IDs. The adapter preserves original evidence strings and excludes malformed/unknown evidence from P-SESSION checkpoints. Image URLs are never fetched; the released `blip_caption` text is included and all outputs are labelled text-only.

## Local preparation commands

```bash
git clone --branch feat/cacheflow-6h --single-branch <private-repo> cacheflow-v2
git switch -c feat/cacheflow-v2-locomo
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev]'
PYTHONPATH=src .venv/bin/python scripts/v2_locomo.py audit \
  --source data/raw/locomo10.json --tokenizer-path <pinned-tokenizer-snapshot> \
  --output results/v2/fit_report.json --output-tokens 64
```

The private Git credential is supplied outside the repository. The LoCoMo source JSON and tokenizer cache are ignored. No old-host serving or timing baseline was run.

## Next execution gate

The tokenizer fit audit and frozen conversation-level split are documented in `docs/V2_DATA_FIT.md`. Both 30-request pilot traces were generated and checked for ordering, size and SHA. Prepare the serving environment and measure 32K memory feasibility before E1/E2. V2 performance claims require a working engine and matched new-host runs; data preparation alone does not establish a latency result.
