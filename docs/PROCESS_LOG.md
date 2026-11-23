# Process log: how this project was built, in order

Written to be read in one sitting. It records what was done, why, what the result was, what went wrong, and which claims changed. The numbers are in the per-study documents (linked); this file is the story. Dates are host/session dates (2026-11-22 and 2026-11-23 for everything after the setup).

## 0. Where things are

| What | Where |
|---|---|
| Repository | GitHub `NguyenDucAnforwork/cacheflow`, branch `feat/cacheflow-6h` (private) |
| Overview, results, commands | [README.md](../README.md) (start here), [interview_brief.md](interview_brief.md) |
| Per-study results and pre-registrations | `docs/*_results.md`, `docs/*_prereg.md` |
| Durable local copy (the GPU host is not persistent) | `C:\Users\ADMIN\.ssh\cacheflow-real-workload\` (`code/` and `results/`) |
| GPU host | Vast.ai RTX 3090 instance, alias `test_sd`; `/workspace` is **not** a persistent volume |

## 1. Phase A: access, host, reproduction

- Goal: apply for an AI inference engineer role (FPT Smart Cloud) with a concrete, defensible project: CacheFlow, a single-GPU serving experiment (vLLM + LMCache CPU KV tier + an admission gateway) that already existed on branch `feat/cacheflow-6h` as a six-hour sprint with a negative headline (the original delay-hit-aware admission, DHAS, did not help; the CPU tier did).
- First steps: SSH into the rented host, measure network, GPU, RAM and disk (RTX 3090 24 GB, 31 GB RAM, 12 vCPU, 50 GB disk). The SSH keys are passphrase-protected and no agent runs, so access goes through a temporary `SSH_ASKPASS` helper that reads the passphrase from a local `.env` and is deleted after use. **Rule adopted from this point: never print secrets to the terminal.**
- Network: the PyPI CDN was throttled to tens of KB/s while a plain speed test looked fast; the pinned packages were installed from a third-party PyPI mirror (disclosed in the docs).
- Reproduced the stack (vLLM 0.22.0, LMCache 0.5.3, Qwen3-1.7B pinned revision), got B1 / B2 working and the unit tests passing on the new host. Pitfalls met: Windows CRLF line endings broke shell scripts on the host (twice), a patch bug in the benchmark client (`SyntaxError`), and a reproduction run that appended rows to tracked result files (append-only, not used).

## 2. Phase B: real mixed workload (study 1)

- The spec given: extend CacheFlow on a 60-minute budget with real data (QuALITY documents + ShareGPT chat), per-class SLOs (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms) and goodput, comparing B1, B2 and B2 with a larger prefill budget. I judged it feasible and did it.
- Outcome ([real_workload_results.md](real_workload_results.md)): the CPU tier removes 48% of computed prefill under burst and raises goodput 2.54 to 4.00 req/s; a larger prefill budget helped further; chat still missed its SLO under burst.
- Honest caveats recorded: one seed, 20 chats, outputs not deterministic even at temperature 0.

## 3. Phase C: "propose next experiments", narrowed by you

- I first proposed many experiments; you narrowed it: a few deep ideas, a natural research question, real data, no mechanical patches, fit in about an hour, skip observability and packaging.
- Resulting study 2 ([chunk_study_results.md](chunk_study_results.md)): 20 runs, 60 chats, three loads, pre-stated hypotheses H1 to H4. Findings: the larger budget helps at every load (but only 11.8% at burst, below my 20% guess), it lengthens inter-token stalls 2 to 3x, under burst chat TTFT is mostly gateway queueing, and chat-first admission moves the SLO miss from chat to documents.
- Corrections made while writing: I had claimed gateway wait was about 2 ms under burst (the data said 1.4 to 1.7 s), and had misread a vLLM metric as a step counter. Both fixed in the docs.

## 4. Phase D: studies 3 to 4 (queue order, step cost, replication, slack)

- Study 3 ([policy_study_results.md](policy_study_results.md)): added two load levels, an age-capped promotion policy, and an isolated prefill probe. Chat-first is nearly free below saturation (seed 7, 0.5 s spacing); age cap too eager; a scheduler step costs about 12 ms.
- Study 4 ([replication_slack_results.md](replication_slack_results.md)): new document set (seed 11); chat-first at saturation replicates but the load at which FIFO fails does not transfer; a slack-promotion policy found no load where both classes meet target.
- Pattern that started here: **hypotheses and thresholds written before the runs** (`*_prereg.md`), failures reported as failures.

## 5. Phase E: "the results look unimpressive", survey, demotion (study 5)

- You pointed out the results were not impressive. My diagnosis: many null results, and no capacity metric that makes configurations comparable. You asked for a proper literature survey and a critique of what is feasible for this problem.
- Survey: keyword groups chosen from the measured bottlenecks; three papers read in full or mostly (FlowPrefill, a client-side overload-control paper, part of SLOs-Serve); feasibility checks on the host (vLLM flags, BurstGPT availability) and an offline headroom estimate from existing data. Most "advanced" techniques were rejected for this setup (disaggregation needs two GPUs; operator-level preemption has no code; adaptive chunking does not fit a workload with short decodes; non-prefix reuse does not apply). Table in README section 5.2.
- Chosen: gateway-level overload control. Study 5 ([demotion_results.md](demotion_results.md)): demote documents that can no longer meet their SLO (still served). Small, set-dependent effect, no added capacity; one pre-registered threshold missed by 0.005.

## 6. Phase F: capacity metric, engine priority, real arrival structure, mechanism (studies 6 and 7)

- Study 6 ([capacity_priority_results.md](capacity_priority_results.md)): defined SLO-constrained capacity (highest load that still meets chat >= 0.95 and doc >= 0.90), built a ladder across configurations, tested vLLM's own priority scheduling, and re-timed traces with BurstGPT arrivals. A control (added after the fact, labelled post hoc) showed the engine-priority gain was not the wider gateway.
- Study 7 ([robustness_mechanism_results.md](robustness_mechanism_results.md)): third document set, a heavier load level, and a gateway-width sweep. **Mechanism found: ordering takes effect in the first queue where requests wait; an FCFS queue upstream defeats it** (gateway chat-first falls from chat SLO 0.94 to 0.57, FIFO level, once the gateway admits more requests than the engine runs).

## 7. Phase G: documentation

- Wrote the README as a complete overview (data, research questions, literature, setup, results, failures, limitations, reproduction) with three Mermaid sequence diagrams (rendered to verify), and exact per-study command lists. Re-running the offline analyses revealed two analysis commands that failed on the full registry; fixed.
- Rule: every push is explicitly approved by you; a commit is made locally first.

## 8. Phase H: combination, hardening (studies 8 and 9): the headline changes

- Study 8 ([combo_results.md](combo_results.md)): engine priority + demotion. **My first design did not bind** (document cap of 16 almost never reached with 42 documents), which I found from a queue-wait diagnostic. It was effectively a second replicate of engine priority and revealed replicate-to-replicate differences of up to 0.095 in doc SLO. A corrected design (cap 4, chosen by a rule fixed from earlier data and labelled post hoc) did not raise any capacity bracket.
- Study 9 ([hardening_results.md](hardening_results.md)): six runs per decisive cell, run-level bootstrap. **The seed-7 capacity gain of 1.9x did not survive: it is 1.7x**, engine priority passes a heavier level than gateway chat-first on 1 of 3 seeds (not 2), and chat-first + demotion is the most consistent configuration. All affected statements in the README and earlier documents were corrected, with correction notes.

## 9. Phase I (this session): investigate the spread, harden the ladder, test the explanation (study 10)

1. **Offline variance investigation** ([variance_investigation.md](variance_investigation.md)): four candidate explanations for engine priority's larger run-to-run spread. Not more unstable requests, not noisier per-request timings; the documents' outcomes within a run are positively correlated for engine priority (variance inflation 1.94) and compensate for demotion (0.30).
2. **Ladder hardening** ([ladder_capsweep_results.md](ladder_capsweep_results.md), Part L): 32 more runs on the boundary cells; all three pre-registered hypotheses met; seed-7 ladder 4.0 to 5.5 to 6.9 req/s (1.7x over B1); the same ordering on seeds 11 and 23.
3. **Cap sweep** (Part M): a causal test of the explanation (lower the document cap, the correlation should drop in a dose-response way). **All three pre-registered hypotheses failed**: only cap 4 reduced the variance, caps 8 and 12 did not, and cap 4 costs document attainment. The explanation stays a hypothesis. Chat-first + demotion without a cap remained the most robust configuration (3 of 4 cells, lowest spread).

## 10. Claims that changed over time

| Claim | First said | Now |
|---|---|---|
| The larger prefill budget cuts burst chat p95 by >= 20% | hypothesis H1 (study 2) | -11.8%, "partly" |
| Gateway wait is about 2 ms under burst | draft of study 2 | wrong; it is 1.4 to 1.7 s (corrected) |
| Engine priority raises capacity 10% beyond chat-first (7.6 vs 6.9 req/s) | study 6 | no: all class-ordering policies tie at 6.9 req/s on seed 7 |
| Capacity gain over B1 on seed 7 is 1.9x | study 6 | **1.7x** (studies 9 and 10) |
| Engine priority beats gateway chat-first on >= 2 of 3 document sets | study 7 (R2) | 1 of 3 after 6 repeats |
| The best configuration is engine priority | after study 6 | chat-first + demotion is the most robust in the decisive cells |
| The spread of engine priority is caused by queueing in the engine's FCFS queue | working explanation (study 10) | consistent with the data but only supported at the extreme cap; not established |

## 11. Principles that held, and what I would do differently

- Held: pre-registered hypotheses; paired comparisons over request IDs and, later, run-level statistics; negative results kept; post hoc steps labelled; one factor changed at a time; secrets never printed; pushes only on approval.
- Did not hold at first: two-repeat cells were treated as decisive; a design was run before checking that its main knob (the document cap) would bind; some drafted numbers were wrong. Each was found and fixed, and the fixes are visible in the history.
- Do differently next time: run a binding check and a pilot of the knob before the full run; aim for 5 to 6 repeats on any cell that decides a conclusion from the start; commit the pre-registration before launching the runs so that ordering is visible in the repository history.

## 12. Re-running anything

All analyses run offline from the committed data (README section 12.4). Serving runs need the GPU host and the pinned stack (README section 12.1 to 12.3); every run is a cold restart and takes about 1.2 minutes. The 374 runs took roughly 8 GPU-hours in total.
