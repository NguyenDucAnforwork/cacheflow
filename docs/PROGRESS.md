# CacheFlow V2 progress and server handoff

Updated: 2026-10-25 (Asia/Bangkok). Work was paused at the owner's request so Codex running **on `optim`** can continue. This file reports completed work and unfinished setup; it contains no credentials.

## Source of truth and owner decision

- Private repository: `NguyenDucAnforwork/cacheflow`, branch `feat/cacheflow-v2-locomo`.
- V2 branch was created from V1 `feat/cacheflow-6h` commit `ef8892e53ff9cb04486707e2844f2535277b9888`. The first V2 checkpoint was pushed as `1847b62fa5b1abcebab0def63699eb41037af972`. Use the latest branch HEAD for the launcher scripts and this handoff.
- The owner explicitly **skipped M1 old-baseline restoration**. Do not rerun old synthetic baselines as a prerequisite. Later B1/B2 runs are new, matched V2 experimental arms, not cross-host comparisons with V1.
- The full proposal is `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`; execution settings are `configs/v2_experiments.yaml`. Preserve all V1 results and research logs.

## Completed and verified

1. New-host inventory was recorded in `docs/V2_NEW_HOST_REPRO.md`: RTX 3090 24 GiB, driver 595.71.05, 125 GiB RAM, 25 GiB overlay disk; `/workspace` is **not** a persistent volume. `/venv/main` has Python 3.12.15 and PyTorch 2.11.0+cu128.
2. Official LoCoMo source was pinned at `snap-research/locomo` commit `3eb6f2c585f5e1699204e3c3bdf7adc5c28cb376`; `locomo10.json` SHA256 is `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. Raw data is ignored by Git (source license CC BY-NC 4.0).
3. Parser, text-only full-context P-QA and chronological P-SESSION prompt adapters, seeded open-loop arrivals, trace SHA checks and V2 streaming replay were added. Gold answers and evidence labels are excluded from prompts. Malformed evidence is preserved for audit and excluded from session checkpoints. Image URLs are never fetched; released captions are used.
4. The Qwen3-1.7B tokenizer fit audit at model revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` found 1,986 QA in 10 conversations: **0/1,986 fit 12,288 tokens; 1,986/1,986 fit 32,768 tokens**, including a 64-token output reserve. Input p50/p90/max = 26,823 / 29,374 / 29,390. All 1,986 prompts retained an exact tokenized common context prefix. Details and per-conversation counts are in `docs/V2_DATA_FIT.md` and `results/v2/fit_report.json`.
5. A deterministic 6/2/2 split by conversation ID is frozen in `configs/v2_experiments.yaml`. Local 30-request P-QA and 30-request P-SESSION pilot traces were generated for `conv-26` and `conv-30`; generated prompt traces are ignored and must be regenerated on the server. A 2K/50 ms E1 prefix-probe trace was also generated locally.
6. Local validation: **10 pytest tests passed**, V2 Python files compiled, and all new shell launchers passed `bash -n`. The V2 branch's first checkpoint was pushed. New launcher scripts in the latest branch were inspected syntactically only; no serving process has been started with them.

## Exact server state at pause

- SSH alias `optim` works; the complete `/etc/vast-agents-guide.md` was read before server actions.
- There is **no completed CacheFlow clone on the server**. An authenticated clone over the slow link was interrupted and its incomplete `/workspace/cacheflow` directory was removed. The temporary GitHub credential and askpass script were removed. The server has no credential left from this work.
- `/workspace/locomo10.json` is a complete raw LoCoMo file and its SHA256 matches the value above. Move it into the repo's ignored `data/raw/` after cloning.
- A pinned model download was interrupted on request; partial files remain in `/workspace/.hf_home` (~16 MiB at pause). Resume the same `snapshot_download` revision, do not treat the snapshot as complete.
- The dependency install was interrupted on request (`/workspace/v2-install.exit` = 143). The model download likewise exited 143 (`/workspace/v2-model.exit`). At pause, `/venv/main` still had PyTorch 2.11.0+cu128 but **vLLM, LMCache and transformers were absent**. The original `uv` resolution/download was slow; inspect `/workspace/v2-install.log` and disk before retrying. No inference service or GPU benchmark was running.
- Approximate overlay usage at pause was 194 MiB of 25 GiB. `/workspace/v2_install.sh`, `/workspace/v2_model_download.sh` and their logs remain as setup records; neither process is running.

## Resume on the server

1. Read `/etc/vast-agents-guide.md`. Establish a private Git credential through the server Codex's approved mechanism, then clone **branch `feat/cacheflow-v2-locomo` into `/workspace/cacheflow`**. Do not clone over `/workspace` itself or put a token in a Git URL/config/log. Verify Git HEAD and a clean tree.
2. `mkdir -p /workspace/cacheflow/data/raw && mv /workspace/locomo10.json /workspace/cacheflow/data/raw/locomo10.json`; verify SHA256. Check `df -h /workspace` and `vast-capabilities | jq '.instance.workspace_is_volume'` again.
3. Resume the pinned Qwen model revision under `HF_HOME=/workspace/.hf_home`. Validate the snapshot before serving. Install a compatible vLLM/LMCache/transformers stack in `/venv/main` after inspecting the interrupted install log. Keep a version report in `docs/V2_NEW_HOST_REPRO.md`. Do not install a new NVIDIA driver.
4. Use `scripts/v2_install_services.sh`, `scripts/v2_start.sh` and `scripts/v2_stop.sh` from the latest branch **after reviewing them on the server**. They are unvalidated launchers. First start B1 at 32K with an 8 GiB GPU KV budget, run one request, record VRAM and errors, then decide whether 4 GiB or concurrency >1 is feasible. This is a V2 memory/serving pilot, not M1.
5. Regenerate ignored trace files with `PYTHONPATH=src /venv/main/bin/python scripts/v2_locomo.py trace --source data/raw/locomo10.json --tokenizer-path /workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e --output data/processed/v2/pilot_pqa_interleaved.jsonl --protocol p_qa --arrival interleaved --sample-ids conv-26 conv-30 --max-model-len 32768 --max-questions-per-sample 15 --qps 2 --seed 7`.
6. Only after the memory/endpoint pilot succeeds, run E1 producer/follower feasibility using `scripts/v2_prefix_probe.py` and `cacheflow.v2_replay`, with GPU/CPU cache state and metrics captured. **Do not implement B5** unless E1 shows a repeatable avoided-prefill or restore opportunity. Add every actual run to `results/v2/registry.csv` and update `docs/main_results.md` with measured results and limitations.

## Open work and known limits

- No V2 latency, CPU restore, answer-quality or GPU memory result exists yet. No full sweep was started.
- The new supervisor launchers and V2 replay have only local syntax/unit validation. Server-side API/ABI and OOM behavior remain unverified.
- The existing V1 scripts contain `/workspace` and `/venv/main` assumptions. The new V2 launcher scripts derive the repo root but have not been exercised; resolve any path issues on the server and record them in `docs/V2_NEW_HOST_REPRO.md`.
- `scripts/v2_locomo.py` and `scripts/v2_prefix_probe.py` generate local JSONL prompts, which are ignored by Git. Regenerate from the pinned source and compare manifest SHA before paired experiments.
- AgentPerfBench is a measurement-method reference; its public result rows do not provide literal prompt-prefix topology for a direct CacheFlow leaderboard comparison.
