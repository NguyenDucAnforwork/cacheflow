# Pre-registration: ladder hardening and a document-cap sweep

Written before any of these runs. Context: [hardening_results.md](hardening_results.md) found that run-to-run spread in doc SLO differs by configuration (SD 0.010 to 0.018 for chat-first + demotion, 0.019 to 0.039 for gateway chat-first, 0.025 to 0.041 for engine priority), and an offline investigation ([variance_investigation.md](variance_investigation.md), `python -m cacheflow.variance_investigate`) showed that this is **not** because engine priority has more unstable requests or noisier per-request timings (corr(unstable count, SD) = -0.08; median per-request TTFT SD is smallest for engine priority, 33 ms), but because its per-document outcomes are positively correlated within a run (variance inflation of the outcome, "design effect", 1.94, versus 1.26 for gateway chat-first and 0.30 for demotion), together with more of its documents sitting within 0.5 s of the 3 s SLO (0.20 vs 0.10 for demotion; corr with SD 0.66). The working explanation, untested, is that queueing in vLLM's first-come-first-served waiting queue builds up as a run-wide shift that moves many near-threshold documents together, whereas demotion absorbs a shift in documents that were going to miss anyway.

## Part L: extend run-level hardening to the rest of the capacity ladder

Cells chosen by a rule fixed before running: every ladder cell with only 2 runs that determines a configuration's bracket (heaviest pass or first failure) and is within 0.06 of a threshold on some class without the other class clearly failing (chat < 0.85 or doc < 0.80). Applying the rule and dropping cells that are not boundary-defining (for example a configuration's pass far below its first failure) leaves the cells below, each of which gets 4 more runs (r3 to r6, 6 in total):

- seed 7: B1 mid65, B2 mid65, B2TP mid50, B2TD mid50, B2TV mid50
- seed 23: B2TP mid50, B2TD mid42
- seed 11: B2T mid50

(8 cells x 4 runs = 32 runs.)

Same pass rule as before (mean chat >= 0.95 and mean doc >= 0.90 over the cell's runs; run-level bootstrap intervals).

- **L1:** seed 7, the CPU tier raises the capacity bracket: B1 fails mid65 and B2 passes mid65.
- **L2:** seed 7, B2TP, B2TD and B2TV all pass mid50 (so the seed 7 ladder tops out at mid50 for the three class-ordering policies).
- **L3:** seed 23 B2TP passes mid50 and B2TD fails mid42; seed 11 B2T passes mid50.

A hypothesis that fails is reported as failed and the corresponding bracket in the README is changed.

## Part M: document-cap sweep for engine priority + demotion

The explanation above predicts a dose-response: if queueing in the engine's FCFS waiting queue causes the common-mode correlation, then moving queueing for documents to the gateway (where demotion acts) by lowering the cap on documents in flight should reduce the variance inflation of the outcome. Configuration `engine_demote` (chat bypasses the cap and is ordered by engine priority; documents capped at N in flight at the gateway and admitted in demotion order). Caps N in {4, 8, 12}; N = 16 did not bind and is equivalent to engine priority alone (B2TV), which is the "no cap" end. Decisive cells as in the hardening study (seed 7 mid45, seed 23 mid45, seed 11 mid42, seed 11 burst), 6 runs each; N = 4 already has 2 runs per cell (attempt 2 of study 8), so 4 more are added; N = 8 and N = 12 get 6 runs (4 x 6 + 4 x 6 + 4 x 4 = 64 runs). Random run order within repeat blocks.

- **M1 (dose-response):** the mean over the 4 cells of the outcome design effect (variance of the per-run mean of the document outcome relative to independent requests) increases with the cap: DE(4) < DE(8) < DE(12) < DE(B2TV).
- **M2 (a useful cap exists):** at least one of caps 8 and 12 passes at least 3 of the 4 decisive cells (the number chat-first + demotion passes).
- **M3 (stability):** the mean run-to-run SD of doc attainment at the best-passing cap is at most 0.02.
- **M4 (descriptive):** report doc and chat attainment per cap and cell, to see whether the cost of a low cap at lighter loads (seen at cap 4) disappears at 8 or 12.

If M1 fails, the common-mode explanation of the spread difference is not supported by this intervention and is reported as such. M2 and M3 decide whether the combination is worth recommending.
