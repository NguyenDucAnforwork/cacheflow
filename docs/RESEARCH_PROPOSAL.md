# /goal — CacheFlow: Delay-Hit-Aware Single-GPU LLM Serving (6-hour autonomous sprint)

You are an applied LLM systems research engineer, operating **now** in an environment with access to a rented NVIDIA RTX 3090 (24 GB) for only about 3–4 GPU-hours, and **six total wall-clock hours** to deliver a reproducible GitHub project. If actual resource availability differs, inspect it and adjust. Start immediately; do not stop at a plan.

## Mission and research contribution

Build and empirically evaluate a **single-GPU, two-tier KV-cache serving pipeline** using vLLM + LMCache and an original, lightweight **Delay-Hit-Aware Admission Scheduler (DHAS)** at the request-ingress layer.

Research question: **When concurrent requests share a long prefix that is not yet resident in cache, can bounded deferral and cache-locality-aware admission reduce redundant prefill and improve end-to-end latency/throughput, without excessive queueing or fairness penalties? How do CPU↔GPU transfers and CPU scheduling overhead affect the answer?**

This is inspired by, but must NOT be represented as a reproduction of, *Strata* (OSDI 2026). It is a scoped engineering experiment for a single GPU—not a claim of a new fundamental algorithm. The essential deliverable is a tested working implementation with causal measurements and negative controls, even if there is no performance improvement.

The project must go beyond simple configuration tuning or a scalar break-even predictor. Actually implement and benchmark a scheduling/admission policy, measure its host-side overhead, and distinguish GPU cache hits from **LMCache CPU-restored** KV. Prefer a small, defensible contribution over multiple incomplete optimizations.

## Source material — read before implementation

1. **Strata: Hierarchical Context Caching** (OSDI 2026): https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang . Focus on *delay hits*, cache-aware scheduling and hiding cache-loading stalls. Cite appropriately; do not claim its throughput figures as ours.
2. **LMCache official repo + MP quickstart** (2026): https://github.com/LMCache/LMCache and https://docs.lmcache.ai/getting_started/quickstart.html . Prefer `LMCacheMPConnector` + `lmcache server`, with version pins. Use in-process integration only as a clearly labeled fallback.
3. **LMCache MP metrics and traces**: https://docs.lmcache.ai/mp/observability/metrics.html and https://docs.lmcache.ai/mp/observability/traces.html . Distinguish cache lookup, store, retrieve, GPU staging/gather and DMA.
4. **Official LMCache Bench**: https://docs.lmcache.ai/cli/bench.html . Workloads include `long-doc-qa`, `multi-round-chat`, `random-prefill` and cache-tier pressure. Use existing commands for cross-checking, plus a custom fixed-arrival trace for the scheduler ablation.
5. **vLLM production metrics**: https://docs.vllm.ai/en/latest/usage/metrics/ . Capture KV usage, prefix hits, running/waiting requests, TTFT and inter-token latency. Confirm names against installed versions.
6. **SGLang agentic cache hints RFC (2026)**: https://github.com/sgl-project/sglang/issues/27574 . Use only as inspiration for application-aware hints, not as an unimplemented dependency.
7. **LMCache MP configuration**: https://docs.lmcache.ai/mp/configuration.html . IMPORTANT: request metadata forwarding does NOT necessarily enforce `ttl`, `skip_save`, or storage policies in MP mode. Verify every feature before using it.

Use the user's attached Viettel AI Race report *if accessible in the working context* as a methodological reference for CPU/GPU boundary profiling, paired comparisons, per-request latency and experimental controls; do not copy its specialized H200 kernels, scores or hardware assumptions.

## Compute and system limits

- Time: **6 hours wall clock**, of which reserve no more than **3–4 GPU-hours**. Begin with environment/dataset preparation before charging the GPU if possible.
- GPU: **RTX 3090 24 GB**, single-GPU only. CPU RAM must be detected; require enough for a bounded CPU-cache tier (prefer 16–32 GB free). Never exhaust the host or allow uncontrolled swapping.
- Model: **Qwen3-1.7B** BF16 (or another known vLLM-compatible 1–3B model if required by compatibility). Do not use 7B/14B unless the small model fails for a documented reason.
- Do NOT do model training, quantization research, PD-disaggregation, speculative decoding, CUDA kernel development or multi-node orchestration in this sprint.
- Use pinned versions, isolated virtualenv or Docker as appropriate. Cache model files between runs. Limit full server rebuilds/restarts.
- **No assumed win**: correct comparisons and reproducible negative results are more important than attractive but misleading numbers.

## Method — exactly what to implement

### Baselines

B0. vLLM, GPU prefix caching disabled (recompute reference).

B1. vLLM, GPU prefix caching enabled, normal FIFO arrivals (strong baseline).

B2. vLLM + LMCache **CPU RAM KV tier**, FIFO arrivals (strong two-tier baseline).

B3. **Same B2 stack** but route requests through a custom, bounded-delay ingress scheduler; hold all other engine settings identical.

If valuable and affordable, B4. B2 + static prefix grouping (simple scheduling control) to isolate whether adaptive/guard logic earns its complexity.

Make sure any "CPU restore" claim is backed by LMCache restore/lookup counters **after GPU eviction**. Vary the number of distinct long prefixes and cache budgets to create actual capacity pressure; do not merely repeat the same hot prefix that never leaves the GPU.

### DHAS: concrete scoped contribution

Implement an asynchronous gateway / dispatch component in Python (`asyncio`/FastAPI or httpx), without modifying vLLM internals:

- Preserve **the exact prompt bytes/tokenization and arrival timestamps**; the gateway may change *admission time/order* but not response content.
- Derive cache locality using **tokenized, block-aligned prefix fingerprints** (not simple first-characters hash). Cache only non-sensitive hashes/metadata, no logging raw prompts.
- Track in-flight prefix groups and recently completed prefixes. Detect **potential delay hits** when two long-prefix requests overlap and the first prefix is still being processed/stored.
- Policies: `fifo`, `static_group`, and `dhas`.
- DHAS gives bounded defer priority to requests likely to benefit from an *in-flight producer's* cache, and optionally groups compatible ready requests. Require a hard `max_wait_ms`, bounded queue, age-based fairness/anti-starvation, and cancellation/timeouts. Expose policy parameters in YAML.
- Prefer a readiness signal from the leading request's **first token** on a streaming upstream connection, plus a short cache-store grace if metrics indicate asynchronous stores; do **not** hold until the entire response finishes by default. If first-token instrumentation is impractical, use a transparent bounded-window version, record the limitation, and avoid claiming full delay-hit elimination.
- Set a sane initial min shared-prefix threshold (e.g. 1,024 tokens), max deferral window (e.g. 100–300 ms), and cap queueing at a safe bound. Tune only on the development trace, not the final holdout.
- Record for every request: original arrival time, queue entry, actual upstream dispatch, first-token timestamp, completion, prefix group, inferred/cache-confirmed hit, output tokens and error. **E2E TTFT is measured from original arrival, not from upstream dispatch.**
- The scheduler should be small and comprehensible, ideally <500 lines of core logic. No artificial dropping requests or changing output length to manufacture speedups.

### Workloads

Create deterministic, hashable workloads with a fixed arrival schedule:

W1. Multi-turn agent/chat sessions, repeated system+history prefixes, interleaved sessions.

W2. Long-document QA, multiple questions per document, **bursty simultaneous arrivals** designed to expose delay hits.

W3. Negative control: random/distinct prefixes (little/no reuse) — DHAS should add minimal overhead.

Workload axis: 2K–8K input tokens, 64–128 output tokens, concurrency 1/4/8/16 when feasible; cache pressure **fit / near capacity / exceeds capacity**. Avoid combinatorial explosion: use a compact 6–10-condition experiment matrix covering low vs high concurrency, warm vs cold, and good vs poor locality.

Ensure warmup/cold-cache resets are controlled. Fix `temperature=0`, input sequences, output budgets, request arrival schedule, tokenization, server config, and max inflight across matched arms. Repeat high-value comparisons at least twice, preferably 3x. Never claim statistical significance from 1 noisy run.

## End-to-end profiling: data → response

Instrument the full serving path, not just GPU kernels:

- Gateway arrival → queue wait → dispatch → HTTP parsing → tokenizer (CPU) → vLLM waiting/running scheduling → LMCache lookup → GPU KV hit / CPU KV hit / miss → CPU-RAM staging → H2D transfer → prefill GPU → first token → decode GPU → detokenization/HTTP stream → complete.
- Metrics: TTFT p50/p90/p99 if enough samples, TPOT p50/p90, total throughput output tokens/s and requests/s, error/timeouts, cache-hit tokens, GPU KV occupancy, CPU cache occupancy, restored bytes/tokens, CPU utilization / CPU RSS / context switches, GPU SM/memory utilization, VRAM, GPU transfer and stalls.
- Tools: vLLM `/metrics`, LMCache `/metrics` and optional traces, `pidstat`, `nvidia-smi`, `py-spy`/`perf` if permitted, and **one short Nsight Systems profile** if installed. Do not spend an hour installing Nsight on a rental.
- Build a request trace timeline and at least one representative CPU↔GPU phase/overlap figure. When a specific stage cannot be observed, explicitly report “not instrumented”; **never infer precise CPU/GPU transfer time from broad GPU utilization alone**.
- Separate **server-side TTFT** from gateway-measured **arrival-to-first-token** latency to expose queueing penalties.
- Interpret results by mechanism: fewer duplicated prefill tokens? higher real CPU KV hits? transfer stalls? CPU scheduler/GIL? queue delay? At most one change per ablation.

## Six-hour work plan with hard checkpoints

**T+00:00–00:40 — Architecture/repo/compatibility.** Inspect host resources and installed tooling. Skim current official quickstart and the OSDI paper. Pin exact versions. Clone/init target GitHub repo/branch, setup project skeleton and docs. Start tracking every attempted run. Download/cached model. First meaningful push by T+00:40. If GPU billing is separate, prepare off-GPU first.

**T+00:40–01:30 — Valid server + baselines.** Bring up vLLM and LMCache MP; verify one cold and one warm request. Build B1/B2 and a direct/offload smoke comparison. Confirm CPU KV actually restored. If MP setup fails past T+01:15, take a pre-declared fallback (in-process LMCache, marked legacy) without silently changing the research question. Push.

**T+01:30–02:20 — Workload + profiling foundation.** Deterministic synthetic trace generator, benchmark client, precise original-arrival TTFT, CSV logs; collect GPU/CPU metrics. Analyze baseline bottlenecks and dataset prefixes; ensure cache pressure demonstrably evicts GPU KV and hits CPU KV. Establish B0/B1/B2. Push.

**T+02:20–03:35 — Implement DHAS.** Implement bounded wait, token-aligned prefix grouping, in-flight delay-hit detection, fairness/timeout behavior, streaming first-token tracking. Test concurrency/cancellation/prompt equality. Compare basic B2 vs B3 on a short screening trace. If no meaningful in-flight overlap emerges, redesign workload from observed arrivals rather than fabricating results. Push at T+03:00 and T+03:35.

**T+03:35–04:45 — Ablation + controlled benchmarks.** At minimum FIFO vs static grouping vs DHAS at one pressured/high-locality and one low-locality regime; repeat meaningful A/B comparisons, record uncertainty. Verify queuing and correctness. One short CPU/GPU profiler trace. Push.

**T+04:45–05:30 — Root cause + refinement.** Attribute performance changes from trace: duplicate prefill, CPU restore vs recompute, transfer cost, in-flight wait, GPU utilization, and fairness. Test **one** data-driven refinement (e.g. pressure-aware bypass when cache is already hot, adaptive defer threshold tied to measured prefill duration, or cap on concurrent followers). Reject if not reproducibly better. Push.

**T+05:30–06:00 — Finalize and publish.** Freeze experiments; kill paid GPU processes before billing ends. Run fast tests, export raw measurements and graphs, write concise technical report with failures/limitations, verify reproducing commands, commit and push final checkpoint; give user repo URL, commit, results and exact outstanding work. Never leave a long benchmark running after deadline.

**At T+02:00** if baseline is not fully reliable, abandon the ambitious scheduler for a well-instrumented KV tiering study, still with one substantive controlled improvement (for example compare LRU vs ARC, request-level transfer gating if genuinely supported, or server-supplied policy knobs). Mark change of scope in decisions. **At T+04:30**, no more new dependencies, engine rewrites, or major architecture changes.

## GitHub: mandatory continuous progress pushes

The user already has GitHub authentication/token on the machine. **Discover the existing authenticated repo/remote first**. Do not ask them to paste secrets into chat. Reuse `gh auth status`, Git credential helper, or an existing `GITHUB_TOKEN`/`GH_TOKEN` environment variable. If no repo exists and permission allows, create one with `gh repo create` (default **private** unless the user explicitly requested public) and push branch `feat/cacheflow-6h`; otherwise document the blocker and commit locally until auth works.

- Commit **working, meaningful increments** and `git push` **after every phase and at least once every 30–45 minutes**. Do not wait until project completion to publish progress. Always push `docs/main_results.md` updates along with code. Avoid empty/spam commits.
- Commit/push when a run *fails* but yields an actionable fix/insight (docs + test), not only on success.
- Use descriptive messages: `feat: initial serving baseline`, `feat: workload trace runner`, `feat: bounded delay-hit gate`, `eval: paired performance ablations`, `docs: six-hour findings`.
- Never include credentials in remote URLs, command logs, README, config, process args, notebook cells, commits, Docker image layers or artifacts. Use `.env.example`, `.gitignore`, `git diff --cached` and a secret scan/check before every push. If token is printed accidentally, stop and instruct rotation.
- If push fails, immediately log the exact reason in `docs/decisions.md` and retry at next checkpoint; do not claim code was pushed until remote commit SHA is verified.
- Keep a local experiment registry with Git commit SHA + model hash + run args, so every result points to reproducible source.

## Code spec (minimal but production-reasonable)

```text
cacheflow/
├── README.md
├── pyproject.toml
├── .gitignore
├── .env.example
├── configs/
│   ├── serving.yaml
│   ├── lmcache_mp.yaml
│   ├── policies.yaml
│   └── experiments.yaml
├── src/cacheflow/
│   ├── __init__.py
│   ├── data.py                  # deterministic workloads/trace IDs
│   ├── gateway.py               # streaming proxy + original arrival timing
│   ├── scheduler.py             # FIFO/static-group/DHAS
│   ├── prefix.py                # token-aligned hashes/overlap
│   ├── bench.py                 # fixed-arrival replay with matched comparisons
│   ├── collect_metrics.py      # vLLM/LMCache/CPU/GPU
│   ├── analyze.py               # aggregates, pairwise deltas, figures
│   └── quality.py               # output/semantic sanity check
├── scripts/
│   ├── setup.sh
│   ├── serve_baseline.sh
│   ├── serve_lmcache.sh
│   ├── bench_matrix.sh
│   ├── profile.sh
│   └── final_report.sh
├── tests/
│   ├── test_prefix.py
│   ├── test_scheduler.py
│   ├── test_gateway.py
│   └── test_trace_replay.py
├── results/
│   ├── raw/
│   ├── figures/
│   └── registry.csv
└── docs/
    ├── main_results.md
    ├── ideas.md
    ├── decisions.md
    ├── lessons_learned.md
    └── reproduce.md
```

Five living docs MAX: `main_results.md` for actual metrics, experiment table and current progress; `ideas.md` for hypotheses and priorities; `decisions.md` for architectural and fallback rationale; `lessons_learned.md` for failed attempts and insights; `reproduce.md` for exact setup/run/hash commands. Update throughout the sprint, not just at the end.

## Done criteria (non-negotiable)

**Engineering completion**
- [ ] Repo pushed successfully with exact remote URL + last SHA; 5 docs current.
- [ ] Working vLLM and LMCache environment, version-pinned; repeatable launch/stop.
- [ ] At least B1 and B2, preferably B0, have real results from equivalent workloads; CPU offload demonstrably exercised.
- [ ] DHAS code with bounded deferral + fairness and tests exists, **unless** fallback was invoked at a documented hard checkpoint.
- [ ] Fixed replay corpus with ≥2 positive locality regimes + one negative control; identical arrival schedule and end-to-end clocks.
- [ ] Measured TTFT (arrival and engine), TPOT, throughput, cache hits, CPU utilization/RAM, GPU utilization/VRAM; transfer-level data where available.
- [ ] ≥3 controlled ablation configurations and at least 2 repeated paired measurements on the key comparison.
- [ ] At least one useful critical-path timeline and a bottleneck/root-cause explanation supported by traces, not intuition.
- [ ] No content changes, timeouts, drops or silently altered request budgets; any output deviations reported.
- [ ] Raw CSV/JSON, scripts, at least 2 plots, `docs/main_results.md`, and reproducible report available after GPU terminates.

**Research success — higher bar**
- DHAS reduces duplicate prefill or increases actual cached-prefix reuse, *with* a measurable improvement in arrival-based TTFT/throughput at cache pressure over B2, **and** does not cause unacceptable p90/p99/fairness regression on the negative control.
- Explain when it **loses** (low reuse, already-hot GPU cache, short prompts, costly deferrals, CPU transfer contention).
- Provide a measured mechanism: e.g. requests prevented from starting redundant prefill, cache hit tokens gained, queueing paid, net TTFT saved.
- Aspirational, not promised: ≥15–20% TTFT p50 improvement in targeted high-pressure workload; no >10% p90 penalty on low-reuse control, at matched output correctness.

**If the hypothesis fails**: mark it rejected and document clear evidence, no invented speedup or fabricated leaderboard rank. A negative result with credible profiling and a correct implementation is still a worthwhile research exercise.

## Final message to user at or before 6 hours

Report in Vietnamese, succinctly: remote GitHub repo and last pushed SHA, measured B0/B1/B2/B3 table, best improvement **against B2**, CPU/GPU timeline insight, whether the research claim was supported, wall-clock/GPU-hours used, unresolved issues and exact next action. Distinguish measured numbers from targets and estimates. Never claim external leaderboard participation: this sprint uses a public official benchmark harness, not a verified submit-to-public-competition portal.

Start now: inspect environment, check official recent docs/code, create first commit, then execute. Do not spend the full six hours planning.
