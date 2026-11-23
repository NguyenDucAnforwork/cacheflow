# Interview brief: CacheFlow in two pages

For a conversation about LLM inference engineering (target: FPT Smart Cloud, AI inference). Everything here is backed by a document in this repository; numbers are from one RTX 3090, a 1.7B model, three document sets, and usually 2 to 6 runs per cell.

## The 60-second version

"I built a reproducible harness for SLO-aware serving of mixed chat and long-document traffic on one GPU (vLLM, an LMCache CPU KV tier, and an admission gateway), and used it to answer one practical question: when short interactive requests and long-document requests share a server, what actually moves SLO attainment? I ran 471 cold-restart experiments on real QuALITY and ShareGPT content, with hypotheses written down before each study. The CPU KV tier and class ordering raise the load the server can carry at the SLO by 1.7x on my main trace. More interesting is what did not work and what I had to correct: ordering only moves misses between classes unless capacity changes, priority only works in the first queue where requests wait, and several of my own headline numbers did not survive more repeats."

## The five findings worth leading with

1. **CPU KV tier (LMCache) under working-set pressure**: with the document working set at 1.75x GPU KV, the tier removes 48% of computed prefill under burst and raises the load carried at the SLO by 37% (4.0 to 5.5 req/s on seed 7). Mechanism measured (restored vs computed tokens), not just latency.
2. **Class-aware admission raises capacity by a further 25%** (5.5 to 6.9 req/s) and fixes chat under overload (chat SLO +0.5 to +0.6), at a cost to documents. Replicated on three document sets and two real arrival windows. Total on seed 7: **1.7x over the GPU-only baseline**.
3. **Priority works in the first queue where requests wait.** Gateway chat-first collapses to FIFO (chat SLO 0.94 to 0.57) once the gateway admits more requests than the engine runs, because the excess waits in vLLM's FCFS queue. Engine-level priority avoids that. A design principle for any multi-queue serving stack.
4. **Demotion of requests that can no longer meet their SLO** (still served, later) was the most robust configuration in the decisive cells: 3 of 4 cells passed, the lowest run-to-run spread, the highest mean doc attainment (0.935, with chat 0.963; engine priority with a document cap of 8 or 12 also clears both targets in the mean but by only 0.001 on doc). It adds no capacity by itself.
5. **Measurement matters, and it led to a mechanism**: run-to-run noise in per-class attainment is large relative to the thresholds (doc SD up to 0.04), differs by configuration, and comes from correlated outcomes within a run (variance inflation 1.94 for engine priority vs 0.30 for demotion), not from noisier requests. A pre-registered 3-way decomposition then showed it is the **ordering policy** that decorrelates the outcomes: a gateway queue with FIFO order and a cap of 4, 8 or 12 documents does not (1.65, 1.65, 1.43 vs 1.94 with no cap), adding the demotion order does (0.77 at cap 4, 0.30 for chat-first + demotion). Two-repeat results near a threshold flipped. The mechanism is directly visible in the gateway's demotion flag: of 1,008 documents in the 24 demotion runs, all 66 demoted ones missed their SLO and none of the other 942 did, so the savable documents are insulated and the miss count is just the (small) number of demoted documents.

## Corrections I made (use them, they show judgment)

- "Engine priority beats gateway chat-first" held on 2 of 3 document sets at two repeats and on 1 of 3 at six repeats. The 1.9x headline became 1.7x.
- My first combined design (engine priority + demotion) did not bind: with 42 documents per trace the document cap of 16 was never reached. I found it from a queue-wait diagnostic and reported both attempts.
- A pre-registered dose-response test of my own explanation for the variance **failed** (three hypotheses, all failed); I then ran a decomposition that separated the factors, and two arms (vLLM `max_num_seqs` 4 and 8) collapsed the server, so concurrency inside the engine's own queue could not be varied; I ran the concurrency contrast under FIFO with a gateway cap instead. The mechanism claim therefore rests on the valid contrasts and is post hoc.

## Questions you may get, and honest answers

| Question | Answer |
|---|---|
| Why a 1.7B model? | Cost and fit on one 3090 with room for KV; prefill is cheaper than for 7B+, so absolute latencies are lower. The ordering of mechanisms should transfer; the load levels will not. A 7 to 8B check is my next external-validity test (memory about 6 GB of KV on a 24 GB card). |
| Is this novel? | No technique is new (offload, priority scheduling, deadline-based admission). The contribution is controlled comparison with SLO capacity as the metric, replication, and the mechanism findings (queue placement, variance structure). |
| Why not prefill-decode disaggregation or operator-level preemption? | One GPU, and no released code for preemption; I did a survey and wrote down the reason for each rejection (README 5.2). |
| How do you define goodput/SLO? | TTFT from the scheduled arrival (queueing counts), per class, over all offered requests, no request dropped from the denominator; capacity is the heaviest load level meeting chat >= 0.95 and doc >= 0.90. Goodput in req/s is reported but flatters policies that serve many cheap requests. |
| Arrival traffic realism? | Simulated schedules plus two re-timed BurstGPT windows (integer-second timestamps, compressed); not production traffic. Document content and chat prompts are real. |
| What would you do at FPT scale (NCP inference)? | Treat the SLO-constrained capacity per GPU as the planning unit, place priority at the first queue, add deadline-aware demotion before scaling out, and measure with at least 5 to 6 repeats per decisive cell. Multi-GPU routing and disaggregation then become the next levers. |
| What did you get wrong? | See the corrections above. |
| How confident are you in "demotion is most robust"? | Moderate: 4 cells, 6 runs each, one model; the interval for the key difference at seed 11 burst excludes zero (doc 0.921 vs 0.833 for engine priority), but chat attainment is lower (0.963) and one of its misses is chat at seed 7 mid45. |

## Numbers cheat sheet

| Item | Value |
|---|---|
| Setup | RTX 3090 24 GB, vLLM 0.22.0, LMCache 0.5.3, Qwen3-1.7B BF16, GPU KV 6 GiB (56,160 tokens), working set 98K tokens |
| Data | QuALITY v1.0.1 dev (14 documents of 6 to 8K tokens), ShareGPT V3 (60 chats), BurstGPT windows; 102 requests per trace; 3 seeds |
| Runs | 471 serving runs + a 210-sample isolated prefill probe |
| Seed 7 capacity ladder | B1 4.0, +CPU tier 5.5, +larger prefill budget 5.5, +class ordering 6.9 req/s (1.7x) |
| Scheduler step cost | about 12 ms (CI 10.9 to 13.2) |
| Larger prefill budget (2048 to 8192) | burst chat p95 -11.8%; inter-token stalls 2 to 3x longer (TPOT unchanged) |
| Chat-first at saturation | chat SLO +0.53 to +0.64; doc SLO -0.17 to -0.19 |
| Demotion, decisive cells | passes 3 of 4; doc run SD 0.014 vs 0.033 for engine priority |
| Noise | engine priority doc SD 0.025 to 0.041; demotion 0.010 to 0.018 |
| Demotion classifier, 24 runs | 66 of 66 demoted documents missed; 0 of 942 others missed |
| Outcome design effect (variance inflation) | engine priority 1.94; gateway FIFO with cap 4 / 8 / 12: 1.65 / 1.65 / 1.43; cap 4 + demotion order 0.77; chat-first + demotion 0.30 |

## Claims to avoid

- A general speedup, or that this is a reproduction of Strata, FlowPrefill or SLOs-Serve.
- That engine priority is "the best" or that the 1.9x figure is right (it is 1.7x).
- Anything about larger models, multi-GPU, or production traffic.
- That the variance mechanism is fully proven: the demotion order is the best-supported factor and its insulation effect is directly visible in the gateway flags, but the contrasts are post hoc and the demotion-order-inside-the-engine corner is missing.

## Where to look in the repository

[README.md](../README.md) (overview, diagrams, all commands), [PROCESS_LOG.md](PROCESS_LOG.md) (the story in order), per-study results and `*_prereg.md` files, `results/figures/` (start with `capacity/ladder_runlevel.png` and `hardening/chat_doc_plane.png`).
