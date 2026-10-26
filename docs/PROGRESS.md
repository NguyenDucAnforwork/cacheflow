# CacheFlow V2 progress and server handoff

Updated: 2026-10-26 03:42 UTC (10:42 Asia/Bangkok). This is the handoff for Codex running on the **current** `optim` server. The previous contents described an earlier server and are superseded. No credentials are stored here.

## Start here

- Project checkout: `/workspace/cacheflow-e1`, branch `feat/cacheflow-v2-e1-prep`, HEAD `2cb521c` before this handoff commit. This worktree was clean at the handoff audit. `/workspace/cacheflow` is a separate V1 worktree at `ef8892e`; leave it untouched.
- Proposal: `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`; detailed current-host record: `docs/V2_HOST_2026_10_26.md`; E1 protocol and decisions: `docs/V2_E1_EXECUTION.md`; data fit: `docs/V2_DATA_FIT.md`. `docs/main_results.md` contains older-host V1/synthetic findings; do not compare its timings with the current host as a causal result.
- The owner explicitly waived M1 old-baseline restoration. Continue V2 experiments on this server; do not make M1 a prerequisite. Do not implement B5 unless E1 shows a repeatable cache-work reduction and an end-to-end benefit.
- `/workspace` is a 25 GiB overlay with about 15 GiB free at this audit. `vast-capabilities` reports `workspace_is_volume=false`: files survive stop/start but not instance recycle/destroy. Keep code, docs and small result summaries pushed to GitHub. Raw model weights, LoCoMo JSON and prompt traces are reproducible/ignored.

## Environment and data verified on this server

- NVIDIA RTX 3090 (24,576 MiB), driver 580.178.04; `/venv/main` Python 3.12.15, torch 2.11.0+cu128, vLLM 0.22.0, LMCache 0.5.3, transformers 5.6.2. `scripts/v2_preflight.py` passed. `PYTHONPATH=src /venv/main/bin/python -m pytest -q` passed **16/16** at this handoff.
- Pinned model: `Qwen/Qwen3-1.7B` revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`, snapshot at `/workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`. Both weight shards were checked against exact byte sizes and SHA-256 before adoption; see `results/v2/adopt_aria_model.log`. The slow original download is finished; no downloader is running.
- Official LoCoMo source: `data/raw/locomo10.json`, SHA256 `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. It is ignored by Git. Regenerate it from the pinned source if this instance is destroyed.
- Ignored frozen traces under `data/processed/v2/`: B1 one-QA full-context; two 30-request LoCoMo dev traces; E1 2K/50-ms one-pair, 2K/50-ms four-pair, and 8K/50-ms eight-pair traces. Manifest SHA256 values are in `docs/V2_HOST_2026_10_26.md`, `docs/V2_E1_EXECUTION.md` and each `.manifest.json`. The tokenizer fit report is tracked at `results/v2/fit_report.json`: 1,986 QA, all fit 32,768 with a 64-token output reserve; input-token p50/p90/max 26,823/29,374/29,390. This tokenizer result does not prove all requests fit concurrently in GPU KV.

## GPU work completed here

- **B1 memory/serving pilot:** `v2-b1-fullctx-1qa-auto-r1`, 19,464 input tokens, 1/1 request succeeded, arrival TTFT 2,169.479 ms, peak sampled VRAM 12,090 MiB, 19,464 newly computed prefill tokens. This validates one full-context request at 32K with an 8 GiB GPU KV budget; it is not a 1,986-question benchmark.
- **E1 2K prefix, 50-ms follower, one pair:** three matched B2 FIFO/B3 DHAS crossovers. Each arm in every pair computed 2,071 prefill tokens and cached 2,048 prompt tokens. Follower arrival-TTFT B3−B2 deltas: -38.107, -98.918, +29.216 ms. The third pair reversed arm order. No repeated incremental cache saving; latency difference changed sign.
- **E1 2K/50 ms, four concurrent pairs:** 8/8 requests succeeded in each arm. Both arms computed 8,284 prefill tokens and cached 8,192 prompt tokens. Follower median B3−B2 TTFT: -30.248 ms in this one matched pilot; no cache-work reduction.
- **E1 8K/50 ms, eight concurrent pairs:** 16/16 requests succeeded in each arm on the same vLLM PID 17516 and LMCache PID 17381. Both arms computed 65,704 prefill tokens, cached 65,536 prompt tokens, and read/wrote 256/256 LMCache L1 chunks. Arrival TTFT p50 B2/B3: 6,557.867/6,435.676 ms; follower median B3−B2: -59.128 ms in this one pilot. The loaded-chunk counter was unavailable, not zero. No observed cache-work reduction.
- **Interpretation:** E1 currently gives a negative cache-savings result for the tested conditions. The small TTFT differences are run-level observations, not a causal DHAS win. Do not implement B5 from these data. Additional arrival/eviction controls may be useful if E1 is revisited.

## Result locations and process state

- `results/v2/registry.csv` tracks **11 successful GPU runs, zero request errors**. Five small matched comparisons are `results/v2/*.compare.json`; per-run metric summaries are `results/v2/*.metrics_summary.json`. These are tracked and pushed. The request JSONL, gateway rows and run summaries (including prompt hashes) are under ignored `results/v2/raw/`; do not delete before any audit. Server logs are `results/v2/*.log` and are ignored.
- Last run completed around 03:39 UTC. At 03:42 UTC all three `cacheflow_v2_vllm`, `cacheflow_v2_lmcache` and `cacheflow_v2_gateway` supervisor programs were **STOPPED**; no V2 experiment or download process was running. They are installed and can be started with the V2 scripts. Check health and zero active/queued requests before resets.
- `scripts/v2_e1_screen.sh PREFIX_TOKENS PAIRS FOLLOWER_OFFSET_MS [REPLICATE]` regenerates a frozen E1 trace, runs B2/B3 against the same engine, resets cache between arms and writes a comparison. Allowed prefix sizes: 2048/4096/8192; pairs: 1/4/8; offsets: 0/50/200/500/1000 ms. Existing run IDs are protected against overwrite. `scripts/v2_compare_e1.py` rejects mismatched trace, request IDs, prompt hashes, token counts, process PIDs and failed runs.

## Suggested continuation on this server

1. From `/workspace/cacheflow-e1`, run `git status --short`, `PYTHONPATH=src /venv/main/bin/python -m pytest -q`, and `/venv/main/bin/python scripts/v2_preflight.py`. Read the proposal and current-host E1 record before choosing the next experiment. Do not reinstall the already working stack or restore M1.
2. Move from synthetic E1 probes to a **small LoCoMo dev pilot** using the frozen `data/processed/v2/locomo_dev_2conv_interleaved.jsonl` and then the session trace. Start with the B1 serving gate; inspect per-request errors, exact server prompt-token counts, VRAM and cache counters before broader comparisons. The 30-request traces are open-loop and may pressure GPU KV; treat an overload run as a capacity finding, not a clean latency comparison.
3. For answer-quality work, ensure the runner saves generated text: `cacheflow.v2_replay` supports `--capture-text`, but `scripts/v2_run.sh` currently does **not** pass that flag. Add an opt-in capture path before grading; never put gold answers or evidence labels in prompts. Keep raw generated text ignored or otherwise handle it intentionally.
4. If revisiting E1, screen an arrival or working-set condition that can produce **different** CPU/GPU cache work across B2/B3, then repeat a promising condition with reversed arm order and reset audits. Report missing counters as null. The current tested conditions are negative; B5 remains gated.
5. Update this file and the relevant experiment doc after measured work. Push small code/docs/summaries before the instance is recycled. `origin` is `git@github.com:NguyenDucAnforwork/cacheflow.git`; this server has no stored GitHub token or SSH credential from the transfer, so an authenticated push mechanism must be available in the server session.
