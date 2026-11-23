# Pre-registration: where the queue lives, how many documents run, or the demotion order?

Written before any of these runs. Follows [ladder_capsweep_results.md](ladder_capsweep_results.md): the cap sweep failed its dose-response prediction (M1 to M3), and only cap 4 reduced the variance inflation of document outcomes ("design effect"), at a cost in document attainment. Two readings of that result were left unseparated:

- **(a) location:** the correlation is caused by documents *queueing in vLLM's first-come-first-served waiting queue*; moving the document queue to the gateway removes it.
- **(b) concurrency:** the correlation falls with the *number of documents in flight in the engine*, wherever they queue.
- A third factor is confounded in cap 4: the **demotion order** among the documents admitted at the gateway.

## Design (a 3-way decomposition, all with engine priority for chat: chat 0, doc 1)

Four decisive cells (seed 7 mid45, seed 23 mid45, seed 11 mid42, seed 11 burst), 6 runs each, random order within repeat blocks. Same SLOs, B2, `max_num_batched_tokens` 8192. New configurations; existing series are reused as comparators (same traces):

| Config | Document queue | Documents in the engine | Order among documents |
|---|---|---|---|
| **V** (existing, engine priority, no cap) | engine | up to 16 | FCFS |
| **S4** (new, `max_num_seqs` 4 in vLLM, gateway pass-through) | **engine** | at most 4 (chat shares the 4 slots) | FCFS |
| **F4** (new, `engine_cap`: chat bypasses the gateway; documents capped at 4 in flight at the gateway, FIFO) | **gateway** | at most 4 | FCFS |
| **VD4** (existing, cap 4 with demotion order) | gateway | at most 4 | demotion |
| **D** (existing, gateway chat-first + demotion, 16 in flight in total) | gateway | up to 16 | demotion |

Contrasts: V vs S4 changes concurrency but keeps the queue in the engine (tests b). S4 vs F4 changes only the queue location at equal concurrency (tests a). F4 vs VD4 changes only the demotion order (tests the third factor). 48 new runs (S4 and F4 x 4 cells x 6).

The statistic: the outcome design effect (variance of the per-run mean document outcome relative to independent requests), averaged over the 4 cells, with a 95% bootstrap interval over runs (cell-wise resampling, 1,000 resamples), plus doc run-to-run SD, cells passed (chat >= 0.95 and doc >= 0.90) and mean chat and doc attainment.

## Hypotheses (decided before running)

- **L1 (queue location suffices):** DE(F4) <= 1.0, i.e. a gateway queue with FIFO order and 4 documents in flight already removes the positive correlation (V is 1.94).
- **L2 (concurrency alone does not):** DE(S4) >= 1.3, i.e. limiting concurrency to 4 while the documents still queue in the engine does not.
- **L3 (the demotion order is not the cause):** |DE(F4) - DE(VD4)| <= 0.4.
- **Reading rule:** L1 and L2 both met supports (a) location; L1 failed and L2 failed supports (b) concurrency (both limited configurations reduce the effect); L1 met and L2 failed with L3 failed would implicate the demotion order. Any other combination is reported as inconclusive. Point estimates decide the hypotheses; the intervals are reported and I will say when they overlap the decision thresholds.

If the result is inconclusive I report it as such; no further knobs are tuned afterwards.

## Note added after the runs

The S4 arm (`max_num_seqs` 4) collapsed the server (goodput 0.26 req/s versus about 7.3; nearly every request missed its SLO), so its design effect is undefined and L2 could not be evaluated; the reading rule above did not anticipate a degenerate arm and its printed output ("concurrency") is an artefact. See [locus_results.md](locus_results.md).
