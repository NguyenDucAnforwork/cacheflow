# V2 E1 feasibility execution protocol

Current server changed on 2026-10-26. The 2026-10-25 status and trace notes below are historical for the previous host. See `docs/V2_HOST_2026_10_26.md` for the active setup; its model, packages and ignored traces must be recreated here before GPU runs.

Status on new server at 2026-10-26 03:35 UTC: B1 and four matched E1 pairs completed, including a four-pair concurrency screen. See `docs/V2_HOST_2026_10_26.md` for exact measurements. The 2026-10-25 gate notes below refer to the previous host. The owner waived old-baseline restoration.

## Gate before GPU runs

`scripts/v2_start.sh` now runs `scripts/v2_preflight.py` before stopping or starting any V2 services. The gate checks pinned package versions, runtime imports, the model revision and every shard listed in the safetensors index. On 2026-10-25 15:15 UTC it correctly failed: vLLM, LMCache, transformers, httpx, FastAPI and uvicorn had not finished installing, and model shard 1 was incomplete. The other Codex session owns those detached downloads; do not launch competing installs.

The pinned Qwen3-1.7B snapshot finished downloading at 2026-10-25 15:30 UTC; both weight shards are materialized and the `snapshot_download` process exited successfully. The vLLM/LMCache package install is still active and must pass version checks. Start B1 at 32K with 8 GiB GPU KV first and send one full-context LoCoMo QA request. Record VRAM, server token count and any OOM or context validation error in `docs/V2_NEW_HOST_REPRO.md`. Do not claim a full-context benchmark from tokenizer fit alone.

The E1 pair experiment uses B2 (CPU tier + FIFO) and B3 (same engine + fixed-200-ms DHAS). The same generated producer/follower JSONL and manifest SHA must be replayed for both arms. Generate 2K, 4K and 8K exact token prefixes with follower offsets 0, 50, 200, 500 and 1,000 ms; screen concurrency 1, 4 and 8 pairs. Do a small pilot first, then expand where the trace actually shows cache opportunity. A hot-prefix control and an in-flight producer condition must be labelled separately.

## Commands after the service stack is validated

The ignored LoCoMo source in this worktree is linked to `/workspace/cacheflow/data/raw/locomo10.json`; its SHA256 was rechecked as `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`. The ignored traces were regenerated on this server from the pinned tokenizer snapshot and official source. Because the package install is still running, generation used the already extracted `uv` package cache as a temporary Python import path; the CLI and project code were unchanged. Both 30-request LoCoMo SHA256 values exactly match `docs/V2_DATA_FIT.md` (`5acdf79b...` for P-QA and `fdeb1efd...` for P-SESSION). The one-question B1 full-context trace (`conv-26`) has 19,464 input tokens and SHA256 `1559381e885668d7430a3cf21bc11748ba4e325c2a1805ae9406c7315042c44c`. The first two-request E1 trace (2,048-token prefix target, 50 ms follower) has 2,060/2,059 input tokens and SHA256 `a2e44487457bf1378c0ea6f955588add37208d199f0f939b484de12e502fbc16`. All four manifests passed `load_trace` and `trace_digest` checks. Recheck tokenizer package version once `/venv/main` finishes installing.

Run from the selected server repo root whose supervisor programs point to the same checkout. The raw JSONL contains prompts and stays under ignored `data/processed/v2/` or `results/v2/raw/`.

```bash
PYTHONPATH=src /venv/main/bin/python scripts/v2_prefix_probe.py \
  --tokenizer-path /workspace/.hf_home/hub/models--Qwen--Qwen3-1.7B/snapshots/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e \
  --output data/processed/v2/e1_2k_50ms_1pair.jsonl \
  --prefix-tokens 2048 --pairs 1 --follower-offset-ms 50 --seed 7

bash scripts/v2_start.sh B2 fifo 8
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b2-2k-50ms-r1 data/processed/v2/e1_2k_50ms_1pair.jsonl

# After the first run finishes and gateway health is idle:
bash scripts/v2_set_policy.sh dhas
bash scripts/v2_reset.sh
bash scripts/v2_run.sh v2-e1-b3-2k-50ms-r1 data/processed/v2/e1_2k_50ms_1pair.jsonl
# Return to FIFO with `bash scripts/v2_set_policy.sh fifo` for ABBA.
```

`v2_run.sh` starts the one-second collector before replay and keeps it alive for two seconds afterward. It writes per-request rows and a run summary under `results/v2/raw/`, appends `results/v2/registry.csv`, and writes counter deltas to `results/v2/<run_id>.metrics_summary.json`. For gateway runs it also extracts the matching request IDs into `<run_id>.gateway.jsonl` and rejects a missing or duplicate gateway row. `v2_metrics.py` rejects counter decreases, which indicate a process restart invalidating the run. The run summary records mode, policy, GPU KV bytes, model revision, dependency versions, trace SHA, source SHA where available, error count, and arrival-based TTFT. Counters absent at a healthy baseline are treated as zero when they first appear; missing data after an endpoint error remains null. This distinction was checked against a historical 256-chunk LMCache restore log.

A matched B2/B3 pilot can be validated with `python3 scripts/v2_compare_e1.py --b2 v2-e1-b2-2k-50ms-r1 --b3 v2-e1-b3-2k-50ms-r1 --output results/v2/e1-2k-50ms-r1.compare.json`. The validator rejects failed or unmatched runs, prompt or token mismatches and serving PID changes, then reports per-request arrival TTFT, admission waits and counter deltas. It does not turn a single pilot into a causal result.

## Server auto-resume

`bash scripts/v2_auto_resume.sh UV_INSTALL_PID [MODEL_DOWNLOAD_PID]` waits up to twelve hours for the setup processes. After it exits, the script checks exact versions, installs this checkout and test dependencies into `/venv/main`, runs preflight and tests, regenerates the four ignored traces using `scripts/v2_prepare_traces.sh`, and rechecks them with the installed tokenizer. It refuses to touch V2 services if supervisor configs already exist or ports 8000/8100/18080 are in use. Only then does it install its V2 supervisor programs and run the one-request B1 full-context pilot at 32K and 8 GiB GPU KV. It stops its V2 services on exit and requires one successful request. The detached run log is `results/v2/auto_resume.log`; an active wait or a log entry is not a GPU result.

The follow-on `scripts/v2_e1_after_b1.sh B1_WATCHER_PID` waits for the B1 watcher to finish, verifies the B1 one-request success, then runs the 2K/50 ms E1 B2 FIFO and B3 DHAS pair on the same serving engine. It resets caches between arms, validates matched artifacts with `v2_compare_e1.py`, and stops V2 services on exit. Its detached log is `results/v2/e1_after_b1.log`. A waiting follow-on job is not an E1 result.

The 2K/50-ms one-pair E1 condition completed three matched comparisons. Follower arrival-TTFT differences (B3 minus B2) were -38.107, -98.918 and +29.216 ms; r3 reversed the arm order. All three pairs had equal B2/B3 computed-prefill (2,071 tokens) and cached-prompt (2,048 tokens) counters, with zero external prefix hits. Thus this condition has no measured incremental cache savings from DHAS, and its latency difference is not stable in sign. Screen a higher-concurrency trace before any B5 work. A four-pair 2K/50-ms screen also showed equal B2/B3 computed-prefill (8,284) and cached-prompt (8,192) counters across eight requests per arm. The next screen will use a larger prefix/working set. Run-level summaries and comparisons are under `results/v2/`; raw prompts remain ignored under `results/v2/raw/`.

## Decision rule

A gateway delay is useful only if matched runs show saved newly computed prefill or a beneficial CPU restore **and** lower arrival-based end-to-end TTFT without a tail or low-reuse penalty. The vLLM metrics are aggregate counters, so an apparent change must also be checked against trace equality, warm/cold state and request-level timings. Producer first-token time is not assumed to be the moment KV becomes available. If FIFO and DHAS have equal computed-prefill and cache-source deltas across repeated controlled traces, record a negative E1 result and do not implement B5.

Before any measured comparison, verify the gateway reports zero active and queued requests. `v2_reset.sh` then waits two seconds for asynchronous stores, clears LMCache L1 where active, resets vLLM's GPU prefix cache, and requires a zero L1 gauge. Do not call it with active requests. Record process IDs to prove whether an ABBA crossover used the same engine. Use at least three independent run-level replicates for contrasts pursued beyond the pilot. Do not compare measured V2 timings with the old V1 host as causal evidence.
