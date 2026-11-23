# Pre-registration: robustness of the capacity result, and why engine-level priority wins

Written before any run of these experiments. Follows [capacity_priority_results.md](capacity_priority_results.md). Same host, model, SLOs, B2, `max_num_batched_tokens` 8192, 2 repeats per cell with reversed order on the second repeat.

## Part 1: robustness of the headline

Claim under test: engine-level priority (B2TV: vLLM `--scheduling-policy priority`, chat priority 0, doc priority 1, gateway pass-through with 64 in-flight) reaches a heavier SLO-constrained load level than gateway chat-first (B2TP, 16 in-flight), and the configuration ordering is stable.

New data: a third document set (seed 23: 14 other QuALITY documents and 60 other ShareGPT chats, same recipe, `--seed 23`, prefix `s23`) and a new load level `mid42` (first visits every 0.42 s, between mid45 and burst) on all three seeds. Common grid for the policy comparison: mid50, mid45, mid42, burst, for B2TP, B2TV and demotion (B2TD) on every seed. Seed 23 also gets B1 and B2 (2048) and B2 8192 FIFO at the levels listed in the run plan, to check the ordering. "Pass" = chat SLO >= 0.95 and doc SLO >= 0.90, pooled over repeats and counted over all offered requests; the capacity bracket is the heaviest level passed with every lighter tested level also passed.

- **R1 (ordering on seed 23):** B1 <= B2 2048 <= B2 8192 FIFO <= B2TP <= B2TV (a later configuration never has a lighter bracket), on the levels tested.
- **R2 (headline):** on at least 2 of the 3 seeds, B2TV passes a strictly heavier level of the common grid than B2TP.
- **R3 (seed 11 gap):** on seed 11, B2TV passes mid45 (chat >= 0.95, doc >= 0.90); it has no mid45 cell yet.
- **R4 (no hypothesis):** where each of B2TP, B2TV and B2TD first fails on mid42 and burst, per seed.

If R2 fails, the statement "engine-level priority raises capacity over gateway chat-first" is downgraded to "seed-dependent" in the README and results document.

## Part 2: mechanism of the engine-priority advantage

Two candidate explanations, to be separated by the gateway width (in-flight cap). Engine `max_num_seqs` is 16 throughout.

- **H-order:** engine-side priority ordering (per-step, inside vLLM's waiting queue) is what helps.
- **H-width:** the gain mostly reflects how many requests are in flight / how slots are counted, so gateway chat-first approaches engine priority when the gateway is made wider (queue partly in the engine, FCFS).

Design (seed 7, mid45 and burst): engine priority with gateway width 24 and 32 (configs `B2TV24`, `B2TV32`) and gateway chat-first (engine FCFS) with width 24 and 32 (`B2TP24`, `B2TP32`); existing cells give width 16 (B2TP) and 64 (B2TV engine priority; B2TPW gateway chat-first, which behaved like FIFO). 16 runs.

Decision rule, per (load, width in {24, 32}): compute engine-priority minus gateway-chat-first attainment on both classes. If either class is higher by at least 0.03 and neither is lower by more than 0.03, that cell supports **H-order**. If both differences are within 0.03, it supports **H-width**. Otherwise it is inconclusive. The overall verdict is H-order if both widths support it at both loads, H-width if all four cells support it, else mixed.

Not part of the pre-registration: the explanation of why. Even if H-order holds, the underlying vLLM behaviour (per-step ordering, interaction with the LMCache connector's waiting-for-KV state) would remain untested.
