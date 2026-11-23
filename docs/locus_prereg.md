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

## Addendum 2: a gentler concurrency arm (S8), pre-registered before it was run

S4 collapsed the server, so the concurrency-only contrast is still missing. This addendum adds **S8**: engine priority with vLLM `max_num_seqs` 8 and a pass-through gateway (queue in the engine, at most 8 sequences running, chat sharing them), on the same 4 decisive cells, 6 runs each (24 runs). One pilot run (seed 11 burst, repeat 1) is run first as part of the arm.

- **Degeneracy rule (decided now, unlike for S4):** S8 is declared degenerate, and no inference is drawn from it, if at seed 11 burst goodput is below 4 req/s or the mean attainment (chat and doc averaged over the four cells) is below 0.5. In that case the concurrency-only contrast stays unobtained and I say so.
- **If S8 is not degenerate:** **L2' (concurrency alone does not decorrelate):** DE(S8) >= 1.3. **L2'' (concurrency decorrelates):** DE(S8) <= 1.0. Anything in between is inconclusive. The reading is then: L2' with the earlier F4 and VD4 results supports the demotion order as the decorrelating factor; L2'' would show that a lower number of sequences running in the engine reduces the correlation by itself.

## Addendum 3: S8 is degenerate; the concurrency contrast is run under FIFO with a gateway cap instead (pre-registered before these runs)

The S8 pilot (seed 11 burst, repeat 1) gave goodput 3.31 req/s (below the 4 req/s threshold of addendum 2; chat 1.000, doc 0.071, run duration 19.0 s against about 13 s for engine priority). By the rule fixed in addendum 2 **S8 is degenerate and the remaining S8 runs were not run; no inference is drawn from S8.** Limiting vLLM's `max_num_seqs` changes capacity, not just concurrency (S4 and S8 both fail), so that knob cannot provide the concurrency-only contrast.

A valid concurrency contrast is available under FIFO order with the document queue at the gateway: the cap on documents in flight at the gateway with chat bypassing (policy `engine_cap`, engine priority for chat), which does not reduce capacity. Already measured: F4 (cap 4) design effect 1.65; V (no cap, documents run up to 16 in the engine, engine FIFO) 1.94. New: **F8 and F12** (caps 8 and 12), 4 decisive cells x 6 runs each (48 runs, random order within repeat blocks).

- **K1 (no dose-response of concurrency under FIFO):** DE(F8) and DE(F12) are both within 0.6 of V's 1.94, i.e. at least 1.34 (F4 already is, at 1.65). Then limiting the number of documents in flight, by itself and with FIFO order, does not decorrelate the outcomes, and the demotion order is the factor that does.
- **K2 (concurrency matters):** DE falls monotonically as the cap falls with a total spread of more than 0.6: DE(F4) < DE(F8) < DE(F12) < DE(V) and DE(V) - DE(F4) > 0.6. Then the cap itself reduces the correlation. (Not met by F4 alone: 1.94 - 1.65 = 0.29.)
- Anything else is reported as inconclusive. Same statistic, intervals and cells as above.
