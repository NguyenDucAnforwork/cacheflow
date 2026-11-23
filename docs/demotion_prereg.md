# Pre-registration: demoting doomed documents (`class_demote`)

Written before any run of this experiment. Follows [replication_slack_results.md](replication_slack_results.md).

## Motivation and data that motivated it

Under burst with chat-first admission, 9 of 28 first-visit documents miss the 3 s TTFT SLO even though their full prefill is computed; those documents account for 33% of computed prefill tokens (22% at mid45; 14% under FIFO at burst). Promoting documents that are close to their deadline (`class_slack`) did not help at burst (doc SLO 0.75, below the 1.5 s age cap at 0.85), consistent with spending capacity on documents that are already late. The related literature (SLOs-Serve: delay requests whose SLO is unattainable to protect the rest; a client-side overload controller that never rejects short requests) points the other way: stop spending capacity on doomed requests. I read these papers only partly (see the survey notes); their evidence is weak for this setting, so this experiment is the test.

## Policy

`class_demote` = chat first (as in `class_first`) plus demotion of doomed documents. A document is **doomed** when `waited + est_service > doc_slo`, with `waited` measured from the scheduled arrival, `doc_slo` = 3000 ms (the SLO), and `est_service` = 150 ms if the gateway has seen a matching prefix recently (cache hit; 150 ms is the measured restore/hit service time) or 72 ms per 1,000 prompt tokens otherwise (the isolated probe). Doomed documents are admitted only when no chat and no non-doomed document is eligible (best-effort tier); order is FIFO within a tier. Demoted documents are still served, never rejected, so SLO attainment is counted over all offered requests and nothing is removed from the denominator. Chat is never demoted. The doomed rule is the same signal `class_slack` used to promote (slack <= 0), with the opposite action, and no margin or other parameter was tuned.

## Design

B2, `max_num_batched_tokens` 8192, 2 repeats per cell, reversed order on the second repeat. New runs: seed 7 (`real60` traces) at mid50, mid45, burst; seed 11 (`s11` traces) at mid50 and burst; 10 runs. FIFO and chat-first comparator cells at those loads already exist (same traces; code differs only by added policies). SLOs: chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms; attainment over all offered requests of the class.

## Hypotheses (decided before running)

Comparator = chat-first at the same load and seed.

- **D1** (seed 7, burst; chat-first 0.94 chat / 0.69 doc): demotion raises doc SLO by at least 0.10 while chat SLO drops by at most 0.05.
- **D2** (seed 7, mid45; chat-first 0.94 / 0.83): demotion reaches doc SLO >= 0.90 and chat SLO >= 0.90.
- **D3** (seed 7, mid50; chat-first 0.98 / 1.00): demotion changes neither class by more than 0.03 (no harm where documents have slack).
- **D4** (seed 11, burst; chat-first 0.99 / 0.83): same direction as D1: doc SLO up by at least 0.05, chat down by at most 0.05.

Also reported, without a threshold: number of documents demoted per run and their outcomes (how many still met the SLO, i.e. false positives), split by first visit and revisit; goodput and run duration; whether revisits (cache hits) of a demoted first visit lose their cache benefit.

If D1 fails, the headline "doomed-document demotion recovers doc SLO at saturation" is dropped and reported as a negative result.
