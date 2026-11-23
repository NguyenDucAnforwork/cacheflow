# Pre-registration: statistical hardening of the cells that decide the ordering

Written before any of the new runs. Motivation: study 8 ([combo_results.md](combo_results.md)) measured replicate-to-replicate differences of up to 0.095 in doc SLO (mean 0.035) for one configuration, so several earlier conclusions rest on single passes at 0.90 to 0.92 from two repeats. This study adds repeats to the cells that decide the conclusions and replaces request-level bootstrap intervals (which ignore run-to-run variance) with **run-level** ones.

## Design

Three configurations: gateway chat-first (B2TP), gateway chat-first + doomed-document demotion (B2TD), engine-level priority with a 64-slot gateway (B2TV). Four decisive cells: seed 7 at mid45, seed 23 at mid45, seed 11 at mid42, seed 11 at burst (the cells where the earlier results sat within noise of a threshold or where the conclusion differed between seeds). Each of the 12 cells already has 2 runs (r1, r2); **4 more runs are added (r3 to r6) for a total of 6**, 48 new runs. Run order inside each repeat block is a fixed-seed random permutation of the cells (with a different order per block), to spread host drift across configurations. Same traces, code path, SLOs and cold-restart protocol as before. (B2TV's earlier non-binding variant B2TVD is not included in the main analysis.)

Unit of analysis: the run. For each run and class, SLO attainment is the share of that run's requests meeting the SLO (chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms). A cell's value is the mean over its 6 runs; its interval is a bootstrap over the 6 runs (10,000 resamples). A cell *passes* when the mean chat attainment >= 0.95 and the mean doc attainment >= 0.90. Also reported: the share of bootstrap resamples in which the cell passes ("pass probability"), and the run-to-run standard deviation per class.

## Hypotheses (fixed before running)

- **H1:** B2TV passes at least 2 of the 4 cells and strictly more cells than B2TP.
- **H2:** B2TD passes at least as many of the 4 cells as B2TV.
- **H3 (noise):** the run-to-run standard deviation of doc SLO attainment is at least 0.03 in at least half (6) of the 12 cells, i.e. the earlier noise estimate was not a fluke.
- **H4 (stability of the pairwise ordering):** for the comparison B2TV against B2TP and B2TD against B2TV, I will report in how many of the 4 cells the 95% bootstrap interval of the difference of mean attainment excludes 0 on at least one class. No threshold is set; it is a descriptive count and will be reported as such.

If H1 fails, the sentence "engine-level priority passes a heavier load than gateway chat-first" is withdrawn from the README. If H2 fails, the statement that demotion beats engine priority on seeds 11 and 23 is withdrawn.

Not part of this pre-registration: a variance model, new policies, or more levels.
