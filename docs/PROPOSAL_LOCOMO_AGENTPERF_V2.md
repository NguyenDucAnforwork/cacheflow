# CacheFlow V2 — Realistic Conversational KV Reuse & Cost-Aware Admission

**Proposal / Codex handoff · 2026-10-25**
**Repository (private):** `https://github.com/NguyenDucAnforwork/cacheflow`
**Existing branch:** `feat/cacheflow-6h`
**Status:** PROPOSED. This document is a plan, **not measured results**. Preserve the original repository, its research logs and all recorded runs. Create a new working branch only after checking the remote status.

## 0. Executive decision

**Keep CacheFlow's vLLM + LMCache CPU-tier implementation, but replace the fixed 8-document synthetic revisit trace as the main evaluation.** Use **LoCoMo** for coherent real conversational content and QA ground truth; use **AgentPerfBench** for serving-metric methodology and optional external performance-reference profiles, **not as a directly comparable latency leaderboard**. Keep the old synthetic tests as mechanism-oriented controls.

**Do not immediately implement another adaptive scheduler.** First establish whether concurrent prefix followers incur redundant prefill that external admission can avoid. If vLLM already shares blocks, redirect engineering effort toward cache reuse between sessions, cache-pressure awareness, and prefetch opportunities rather than repeatedly tuning a 200 ms delay.

## 1. Prior work and reproducible baseline

### Previous stack and status

- Single RTX 3090 24 GiB; Qwen3-1.7B BF16, pinned revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.
- Python 3.12.15, PyTorch 2.11.0+cu128, vLLM 0.22.0, LMCache 0.5.3, transformers 5.6.2 (old host only; **do not assume the new host matches**).
- B0: vLLM without prefix caching; B1: GPU prefix caching; B2: B1 + LMCache CPU KV; B3: B2 + DHAS; B4: B2 + static grouping; `dhas_guarded` is a B3 policy variant.
- Strongest positive result: with 8 × 8K synthetic documents at 6 GiB GPU KV, B1 late-revisit mean TTFT ~2.59 s, B2 ~0.33–0.37 s, with 65,536 CPU-restored tokens/run. This is **specific to the pressure-generating trace**.
- Main negative result: DHAS added no cached tokens / saved prefill over FIFO in the recorded comparisons; same-engine ABBA crossover did not support a reproducible benefit; guarded holdout also failed.
- Relevant files: `README.md`, `docs/main_results.md`, `docs/reproduce.md`, `docs/decisions.md`, `results/registry.csv`, `src/cacheflow/{data,bench,gateway,scheduler,collect_metrics}.py`.

**Critical portability issue:** scripts refer to `/workspace`, `/venv/main`, pinned model-cache snapshot directories, supervisor configuration paths and localhost ports. These are old-host assumptions. Audit them before running services.

### Verified source material

1. **Strata, OSDI 2026** — hierarchical CPU/GPU caching, delay hits, I/O and cache-aware scheduling. https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang
2. **EpiCache, ICML 2026** — manages episodic KV under a memory budget; evaluates LoCoMo, LongMemEval and RealTalk. Its KV compression technique is **not equivalent** to our lossless offloading. https://proceedings.mlr.press/v306/kim26ag.html ; https://github.com/apple-aiml-research/ml-epicache
3. **LoCoMo** — original data `snap-research/locomo/data/locomo10.json`: 10 long multi-session conversations, with annotated QA, answer, category and evidence dialog IDs; original dataset paper ACL 2024. https://github.com/snap-research/locomo
4. **AgentPerfBench, Sept. 2026 preprint + public benchmark results** — profiles based on SWE-bench, TerminalBench, OSWorld, ShareGPT and includes TTFT/TPOT/throughput measurements. Its public Hugging Face artifact provides aggregated/performance benchmark results, not an off-the-shelf exact-prefix request corpus. Its reported serving methodology is **closed-loop concurrency**, not open-loop arrival timing. https://arxiv.org/abs/2609.34683 ; https://huggingface.co/datasets/agent-perf-bench/AgentPerfBench
5. **Pinned vLLM arguments:** https://docs.vllm.ai/en/v0.22.0/configuration/engine_args/ ; **LMCache MP quickstart:** https://docs.lmcache.ai/getting_started/quickstart.html

## 2. Research questions (new scope)

**RQ0 — Opportunity / feasibility:** Under which prefix lengths, follower arrival offsets, concurrency and cache residency states does vLLM 0.22.0 actually compute redundant prefill that an ingress scheduler could prevent? Is producer first-token readiness a valid proxy for KV being available, or only a loose upper-stage signal?

**RQ1 — Tiering / workload generality:** How does GPU+CPU KV caching change arrival-based TTFT and throughput on *multi-session conversational QA* compared to GPU-only caching, as a function of reuse distance, working-set pressure and offered load?

**RQ2 — Scheduling / cost-awareness:** Conditional on measurable opportunity, can a bounded admission policy that accounts for producer readiness, cache availability and expected queue cost outperform FIFO and fixed-200-ms DHAS **without increasing p95/p99 or low-reuse regressions**?

**RQ3 — Correctness:** Does cache-tiering and scheduling preserve answer quality, prompt/output budgets and operational fairness? Can all differences be audited, including nonidentical output hashes under `temperature=0`?

### Hypotheses and falsification

- **H0:** Under many concurrent in-flight shared-prefix conditions, vLLM's internal block reuse already removes redundant prefill. If matched B2/B3 aggregate prefill and tier-hit evidence remain equal, the *delay-hit* claim is rejected for those conditions.
- **H1:** B2 improves tail TTFT only when valuable reusable prefixes have left GPU KV but remain resident in CPU RAM; absolute KV GiB alone is not explanatory.
- **H2:** Early admission is best for no-prefix/hot-GPU requests; bounded waiting can help only if expected avoided work exceeds waiting/queue interference. Verify this rather than assuming it.
- **H3:** A scheduler that optimizes internal engine TTFT by moving delay to the gateway **must not count as a win** unless arrival-based E2E latency also improves.

## 3. Dataset and protocol design

### 3.1 LoCoMo raw QA corpus

Input: official `data/locomo10.json`, pin source commit SHA and file SHA256. Preserve speaker, session boundaries, chronological order, timestamps, dialog IDs, text, QA categories, answers and supporting evidence IDs. Do not regenerate fictional conversations or change QA wording to fit the hypothesis.

**Two explicit protocols; never mix scores:**

**P-QA (quality / full-context shared-prefix):** For each conversation, serialize a **fixed, canonical full conversation context** (speaker + session boundaries) followed by one QA question. Different questions for the same conversation share *exact tokenized prefix*. Measure serving performance and score answers against LoCoMo QA annotations. This is the protocol closest to full-history long-conversation QA. If a full context does not fit the serving model, either raise `max_model_len` (after memory pilot) or flag the sample as out-of-scope; **do not silently truncate and call it the standard LoCoMo benchmark**. If a truncation/selection protocol is chosen, label all scores `LoCoMo-derived 12K subset`, not `LoCoMo leaderboard`.

**P-SESSION (serving / sequential conversation):** Construct sessions in chronological order; progressively increase the known history prefix and interleave distinct conversations. Only ask questions at a checkpoint if their evidence was already visible by that checkpoint. Prevent answer leakage: no future sessions, gold answers, QA evidence labels or hidden annotations in the model prompt. This is an **adapted serving replay** and not the canonical LoCoMo QA protocol.

Image handling: LoCoMo's released images are not provided; do not dereference private or third-party image URLs automatically. If using text-only captions, declare the transformation, and do not claim a multimodal benchmark.

**Fit pilot BEFORE GPU benchmarking:** inspect tokenizer-based context-length distribution. Report p50/p90/max; fraction within 12,288 and 32,768 tokens; GPU memory estimated for chosen context limit and concurrent sequences. The original server uses `--max-model-len 12288`; don't promise a full-dataset run without verifying this constraint. Keep first smoke to 1–2 conversations and a limited number of QA; scale only when measured feasible.

### 3.2 AgentPerfBench as reference, not direct leaderboard

Inspect the released schemas/configs before claiming replay capability. The public Hugging Face `trace_replay` config contains *benchmark results* on model/hardware/engine/profile axes, with reported TTFT/TPOT/ITL/throughput; its methodology used closed-loop concurrency and exact input/output-length sequences from agentic tasks, **not necessarily preserved literal prompts and cache-sharing topology**.

Optional follow-on: emulate 1–2 workload profiles (e.g. `swebench-multiturn-short`, `chat-multiturn-short`) *only after* obtaining valid profile-level request sequences. Report this as **profile-inspired workload** if reconstructed. Do not compare our RTX 3090/vLLM 0.22/Qwen3-1.7B latency against published scores for other models, engine versions or GPUs as if it were a public leaderboard rank.

### 3.3 Arrival models and cache locality

Keep prompt content identical between paired configurations, but independently control arrival schedules:

- **Grouped**: questions sharing a context arrive close together; upper-bound locality diagnostic.
- **Interleaved**: different conversations alternate; tests GPU eviction and CPU restore.
- **Low-reuse / distinct**: requests from nonshared contexts, or unique prompts, to measure overhead.
- **Open-loop arrivals**: seeded exponential interarrival times at declared QPS rates; keep original arrival timestamps and allow queues to grow. Add a separately labelled closed-loop profile run only if needed for AgentPerfBench methodology comparability.

**Caution:** neither LoCoMo itself nor these synthetic arrival schedules constitutes production arrival traces. State this honestly. Do not manually time late questions only to guarantee a CPU restore.

### 3.4 Train/dev/holdout splits

Split by `sample_id` (conversation), never randomize individual QA questions across dev/holdout, to prevent shared-history leakage. With only ten conversations, a practical exploratory split is 6 dev / 2 validation / 2 holdout (fixed deterministic IDs; inspect lengths/categories first). Because statistical power is small, repeat serving traces over independent arrival seeds and report uncertainty across **runs**; do not claim general population significance from the ten-conversation sample.

## 4. Experiments (ordered by decision gates)

### E0. Environment + old-baseline reproduction

- Hardware inventory: GPU model/VRAM, driver, CUDA ABI, CPU RAM, disk, Python environment; verify private GitHub authentication.
- Clone original branch; preserve `results/` and `docs/main_results.md`; establish new host IDs and fresh run-ID namespace (`v2-*`).
- Restore pinned vLLM/LMCache and model revision **only if compatible** with the new driver/Python/CUDA. Use original `docs/reproduce.md` as reference; if a package must change, document ABI and do not compare old/new numbers causally.
- Run unit tests first, then B1 smoke, B2 CPU-restore smoke using the existing `scripts/restore_probe.py`; check both LMCache chunk loads and GPU-local absence. Run one B1/B2 paired **small synthetic** sanity check on the new host. This does not become the main V2 finding.

**Gate:** Do not proceed if CPU restore is not demonstrably functioning or if the new server OOMs under the pinned configuration.

### E1. Prefix-sharing feasibility — RQ0

- 2 requests with the same 2K / 4K / 8K prefix, follower offset ∆t = 0 / 50 / 200 / 500 / 1000 ms; selected concurrency 1 / 4 / 8.
- Compare FIFO vs DHAS; reset GPU and CPU caches identically, repeat with a pre-warmed prefix and with the producer in-flight.
- Capture aggregate GPU-hit, external CPU-hit and newly computed prefill tokens; producer first token, follower dispatch, wait, queue, timeouts and trace SHA.
- Determine whether there is *avoidable* duplicate prefill, not just observed matching prefixes.

**Gate:** If there is no reproducible avoided prefill/restore gain, **do not implement B5 adaptive delay-hit**. Investigate tiering or prefetching instead.

### E2. Real-content tiering — RQ1

- Use P-QA fit subset with genuine LoCoMo texts and a declared fixed prompt template; start with ~30–60 QA requests on 2–3 eligible conversations, based on tokenizer fit. Increase later if resource permitting; never label the pilot as full benchmark.
- Conditions (screened matrix): B1 vs B2; GPU KV at 4 GiB and 8 GiB (only if each supports chosen context; add 6 GiB if informative); grouped vs interleaved; low vs moderate QPS calibrated on this new host.
- Hold CPU L1 constant if host memory permits, e.g. 16 GiB. Record GPU/cache occupancy and **CPU restored tokens** to establish a mechanism.
- Include a GPU-fit control to measure B2 overhead without CPU restores.

**Outputs:** paired per-request TTFT, p50/p95/p99 by run, throughput, GPU/CPU hit tokens, new prefill tokens, eviction/restore evidence, memory peaks and graphs versus estimated working-set pressure.

### E3. Multi-session serving — RQ1/RQ3

- Use P-SESSION incremental histories (not fake `4 questions per document`), interleave sessions under open-loop arrival schedule.
- Vary thinking gap/session resumption gap within declared distribution, not only one hardcoded 8.1 second revisit.
- Evaluate B1/B2 and, only after E1 opportunity gate, B3/B5. Measure fairness and tail latency.

### E4. Scheduling ablation — RQ2

Only if E1 establishes a real gateway opportunity. Compare:

| Arm | Stack/policy | Purpose |
|---|---|---|
| D0 | B2 engine direct (no ingress gateway) | isolate gateway overhead |
| B2 | LMCache CPU + FIFO ingress | primary baseline |
| B3 | original fixed-200-ms DHAS | existing heuristic |
| B4 | static-group | simple competitor |
| B5 | bounded cost/readiness-aware admission | **proposed only if E1 validates mechanism** |

Candidate B5 may use measured producer-ready latency buckets, prefix length, current occupancy and estimated transfer/recompute cost. **Do not claim restore-vs-recompute selection**: the current gateway lacks a verified engine API to force that choice. Implement only actions it can actually control (admission/order), unless later verifying a compatible vLLM/LMCache per-request load policy.

Run balanced ABBA crossovers with same vLLM/LMCache processes, uniform warmup and controlled empty-cache reset before each arm. Use >=3 run-level replicates for key contrasts and fresh arrival seeds on holdout. Stop a candidate that merely moves waiting outside engine TTFT.

### E5. LoCoMo answer quality — RQ3

- Run the official full-context QA protocol **only** for examples fitting the selected maximum context length; otherwise a distinctly named fit-subset evaluation. Decide evaluator and prompt template in advance (LoCoMo original implementation or one fixed, cited evaluator). Record exact version and answer normalization.
- Compare answer scores across B1/B2/B3/B5 with **identical exact prompts**. For output-hash mismatches, save redacted generated texts and QA scores, not just hashes. Record token counts, failed requests and output budgets.
- The published EpiCache LoCoMo numbers arise under compression and different model/protocol settings; they are **literature context**, not apples-to-apples serving baselines. Report any leaderboard comparison only when the identical model, prompt/evaluator and subset/protocol are verified.

## 5. Measurement, statistics, reproducibility

Primary metric: **arrival-based E2E TTFT** (scheduled arrival -> first nonempty model text). Secondary: TTFT p95/p99, TPOT, throughput, request-success rate, cache-hit source breakdown, compute tokens, `lmcache` loaded chunks, GPU KV fraction, CPU RAM, queue waiting. Use per-run paired deltas, means and confidence intervals based on independent runs. Distinguish queue-capacity waits from policy-specific deferral deadlines.

Run metadata MUST include: `run_id`, source Git SHA, tokenizer/model revision, experiment plan version, sample IDs, dataset file SHA, prompt template version, tokenizer counts, exact prompt hash, arrival trace hash, request IDs, policy, GPU KV bytes, CPU L1 bytes, max context, output budget, driver/Python/vLLM/LMCache versions, reset mode, start/end times, error status and raw metrics paths.

Preserve existing results; write all V2 artifacts under a separate `results/v2/` tree (plus any newly introduced `data/processed/v2/` ignored as appropriate). Produce generation scripts for plots and CSV tables; sample-level data split IDs should be committed; copyrighted/unlicensed large source data and secrets should not be pushed without reviewing licenses. Keep baseline output hashes, avoid pretending semantic equivalence where only hashes exist.

**Proposed target thresholds (not facts):** in at least one predefined pressured-locality condition, >=10% improvement in p95 E2E TTFT over B2 FIFO with no >5% p95 regression on low-reuse controls, no increased error rate, and a mechanism showing avoided work or increased beneficial restore. If unmet, publish the negative result and characterize the regime where caching is useful.

## 6. Recommended implementation milestones

1. **M0 (CPU-only):** environment inventory, clone repo, path portability fixes, data schema audit, proposal added as new document, data preprocessing unit tests. Keep old code and results unchanged.
2. **M1:** pinned serving stack restored and B1/B2 smoke + restore verification pass; save reproducibility report for new host.
3. **M2:** LoCoMo parser, deterministic prompt builder, full-context fit audit, session adapter, split file and trace SHA integrity checks; <= 2 conversations smoke replay.
4. **M3:** E1 prefix feasibility; decide whether scheduling is worth pursuing.
5. **M4:** E2/E3 run matrix, ABBA repetition, plots, stats and quality audit; include AgentPerfBench methodology comparison as an appendix.
6. **M5 (conditional):** B5 development only if E1 shows missing opportunity; frozen holdout; final research summary, limitations and reproduction commands.

Deliverables: `docs/PROPOSAL_LOCOMO_AGENTPERF_V2.md`, `docs/V2_NEW_HOST_REPRO.md`, `configs/v2_experiments.yaml`, dataset adapter/tests, `results/v2/registry.csv`, figures, updated `docs/main_results.md` **appended in a clearly separated V2 section**.

## 7. New server handoff: safe bootstrap instructions for Codex

### What Codex must know

- This is an **existing private repo**, NOT a new repository. Branch `feat/cacheflow-6h`; do not initialize a new repo or overwrite old work.
- `/workspace` was the old project root, `/venv/main` the old Python virtualenv. `scripts/install_services.sh` writes under `/etc/supervisor/conf.d`; only run it if the new host actually uses supervisor and permissions are appropriate.
- Existing `scripts/serve_vllm.sh` accepts only 4/6/8 GiB and hardcodes `max_model_len=12288`. Do not silently increase either setting or build a full-LoCoMo quality claim until a hardware/token-length pilot is completed.
- Do not install arbitrary latest `vllm`/`lmcache` over the current environment. Check pinned dependency compatibility first. Reuse `/venv/main` if it already exists and works; otherwise create/modify a portable setup on a **new branch**.
- Check `gh auth status` or existing Git credential/SSH integration; never paste/access-token values into the terminal logs or git config URLs. If private clone requires authorization, stop with the exact blocker rather than making a public copy.

### Shell kickoff (safe inspection and clone)

```bash
# On the NEW server — diagnostics, no installs yet:
pwd
id
uname -a
nvidia-smi || true
python3 --version || true
free -h
df -h . /workspace 2>/dev/null || true
command -v git || true
command -v uv || true
command -v gh || true
command -v supervisorctl || true
[ -x /venv/main/bin/python ] && /venv/main/bin/python --version || true
[ -d /workspace ] && ls -la /workspace || true

# Only if /workspace is empty and writable:
# git clone --branch feat/cacheflow-6h --single-branch \
#   https://github.com/NguyenDucAnforwork/cacheflow.git /workspace
# Otherwise clone into a safe NEW directory, e.g. ~/cacheflow,
# and have Codex remove hardcoded paths BEFORE running any service.

# From the selected REPO ROOT, after private clone succeeds:
git status --short
git branch --show-current
git log -1 --format='%H %s'
sed -n '1,120p' docs/reproduce.md
sed -n '1,120p' scripts/serve_vllm.sh
sed -n '1,120p' scripts/install_services.sh
```

### Restore sequence (Codex decisions, not blindly copy-paste on any new host)

1. Verify GPU model, free VRAM, NVIDIA driver/CUDA compatibility, free host RAM/disk. Record full diagnostics in `docs/V2_NEW_HOST_REPRO.md` (omit identifying host secrets).
2. Establish private repo access and clone verified remote/branch into a non-destructive location. Create `feat/cacheflow-v2-locomo` from the latest verified `feat/cacheflow-6h` *after fetching*, without force-pushing.
3. Search for absolute old-host paths (`rg -n '/workspace|/venv/main|cuda13|supervisor|.hf_home' scripts configs src docs`). Refactor to environment-driven `CACHEFLOW_ROOT`, `VIRTUAL_ENV`, `HF_HOME`, or an equivalent portable layout while retaining legacy defaults; add smoke tests for the new paths.
4. Inspect `pyproject.toml` and `docs/reproduce.md`. Create/activate an isolated env; reinstall the historical pins only after verifying GPU/driver/ABI compatibility. Never claim same experimental conditions if versions change.
5. Populate the pinned model via `scripts/download_model.py` using the old revision. Download LoCoMo from the original `snap-research/locomo` repo and record data SHA. Inspect AgentPerfBench dataset card without treating its result parquet as raw prompts.
6. Run `pytest -q` (in the correct env) and existing no-GPU tests; then start B1 and B2 **sequentially**, smoke HTTP health, and run `scripts/restore_probe.py` with local-only endpoints. Do not run capacity sweeps/full experiments until a reproducible CPU KV restore succeeds.
7. Start M2 dataset audits and 1–2-conversation LoCoMo pilot. Record every error and fix into a new host reproducibility document. Commit/push only meaningful validated changes; avoid secrets, model weights and logs containing raw tokens.

### Exact initial Codex task (copy-paste)

> We are resuming my EXISTING private GitHub repo `NguyenDucAnforwork/cacheflow`, branch `feat/cacheflow-6h`, on a NEW GPU server without a local clone. The old repo implements Qwen3-1.7B + vLLM 0.22.0 + LMCache 0.5.3 + asyncio FIFO/DHAS; historical results are in `docs/main_results.md`. The new V2 proposal is `CacheFlow_Proposal_v2_LoCoMo_AgentPerfBench.md` (provided alongside this instruction). **First inventory GPU/driver/CUDA/Python/RAM/disk and Git authentication; clone the existing private repo without overwriting files.** Audit `/workspace`, `/venv/main`, HF model cache and supervisor hardcodes. Create a new V2 branch. Before adding any scheduler optimization, restore a working environment, run unit tests and B1/B2 + CPU KV restore smoke tests, then implement a deterministic LoCoMo parser, full-context length/fit audit, QA/session prompts and replay integrity tests. Use LoCoMo as real conversational QA data and AgentPerfBench only as serving-metric reference; do not invent an exact-prefix leaderboard. Preserve all V1 code/results, record versions and provenance, and stop/report a concrete blocker if the new GPU is incompatible. Deliver new-host reproducibility notes, the LoCoMo data fit report, exact commands/outputs, changed files, test status and the next E1 feasibility experiment. Do not start full sweeps or claim speedups until the environment and prefix reuse are verified.

## 8. References

- Strata (OSDI 2026): https://www.usenix.org/conference/osdi26/presentation/xie-zhiqiang
- EpiCache (ICML 2026): https://proceedings.mlr.press/v306/kim26ag.html
- EpiCache official code: https://github.com/apple-aiml-research/ml-epicache
- LoCoMo original benchmark: https://github.com/snap-research/locomo
- AgentPerfBench preprint: https://arxiv.org/abs/2609.34683
- AgentPerfBench public result dataset: https://huggingface.co/datasets/agent-perf-bench/AgentPerfBench
- vLLM 0.22.0 engine flags: https://docs.vllm.ai/en/v0.22.0/configuration/engine_args/
- LMCache MP setup: https://docs.lmcache.ai/getting_started/quickstart.html
