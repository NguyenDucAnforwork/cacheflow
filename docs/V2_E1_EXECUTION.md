# V2 E1 feasibility execution protocol

Status: CPU-side runner and counter analysis prepared on the new server; no GPU E1 run yet. This document is separate from the V1 reproduction log. The owner waived old-baseline restoration.

## Gate before GPU runs

The pinned Qwen3-1.7B model snapshot and vLLM/LMCache packages must finish downloading and pass version checks. Start B1 at 32K with 8 GiB GPU KV first and send one full-context LoCoMo QA request. Record VRAM, server token count and any OOM or context validation error in `docs/V2_NEW_HOST_REPRO.md`. Do not claim a full-context benchmark from tokenizer fit alone.

The E1 pair experiment uses B2 (CPU tier + FIFO) and B3 (same engine + fixed-200-ms DHAS). The same generated producer/follower JSONL and manifest SHA must be replayed for both arms. Generate 2K, 4K and 8K exact token prefixes with follower offsets 0, 50, 200, 500 and 1,000 ms; screen concurrency 1, 4 and 8 pairs. Do a small pilot first, then expand where the trace actually shows cache opportunity. A hot-prefix control and an in-flight producer condition must be labelled separately.

## Commands after the service stack is validated

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

`v2_run.sh` starts the one-second collector before replay and keeps it alive for two seconds afterward. It writes per-request rows and a run summary under `results/v2/raw/`, appends `results/v2/registry.csv`, and writes counter deltas to `results/v2/<run_id>.metrics_summary.json`. `v2_metrics.py` rejects counter decreases, which indicate a process restart invalidating the run. The run summary records mode, policy, GPU KV bytes, model revision, dependency versions, trace SHA, source SHA where available, error count, and arrival-based TTFT. Missing counters are reported as null.

## Decision rule

A gateway delay is useful only if matched runs show saved newly computed prefill or a beneficial CPU restore **and** lower arrival-based end-to-end TTFT without a tail or low-reuse penalty. The vLLM metrics are aggregate counters, so an apparent change must also be checked against trace equality, warm/cold state and request-level timings. Producer first-token time is not assumed to be the moment KV becomes available. If FIFO and DHAS have equal computed-prefill and cache-source deltas across repeated controlled traces, record a negative E1 result and do not implement B5.

Before any measured comparison, verify the gateway reports zero active and queued requests. `v2_reset.sh` then waits two seconds for asynchronous stores, clears LMCache L1 where active, resets vLLM's GPU prefix cache, and requires a zero L1 gauge. Do not call it with active requests. Record process IDs to prove whether an ABBA crossover used the same engine. Use at least three independent run-level replicates for contrasts pursued beyond the pilot. Do not compare measured V2 timings with the old V1 host as causal evidence.
