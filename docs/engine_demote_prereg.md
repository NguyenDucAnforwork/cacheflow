# Pre-registration: demotion order inside vLLM's own waiting queue

Written before the patch was run. Fills the missing corner of the decomposition in [locus_results.md](locus_results.md): there, the demotion order lowered the correlation of document outcomes (design effect 0.77 with a cap of 4, 0.30 without a cap) only in configurations whose document queue was at the **gateway**; engine priority, whose queue is in vLLM, has no deadline-aware ordering (design effect 1.94). The direct trace showed that the gateway's flag partitions the misses perfectly (66 of 66 demoted documents missed, 0 of 942 others). The open question is whether the ordering helps by itself **inside the engine queue**, or only when applied at a gateway with its own admission cap.

## Implementation (a small, documented patch to vLLM 0.22.0)

`scripts/patch_vllm_engine_demote.py` patches `vllm/v1/core/sched/request_queue.py`: with the environment variable `CACHEFLOW_ENGINE_DEMOTE=1`, `create_request_queue` returns a `DemotingPriorityRequestQueue` that picks the next waiting request by the key (tier, priority, arrival time) with tier 0 for chat (request priority 0), tier 1 for documents (priority 1) that can still meet their SLO and tier 2 for **doomed** documents, those with `(now - arrival_time) + estimated service > 3000 ms`. Estimated service is 72 ms per 1,000 prompt tokens (the isolated-probe value used by the gateway policy). Unlike the gateway rule there is **no discount for a recent prefix match** (the engine cannot see the prefix-cache hit before scheduling), so cached second and third visits are judged slightly pessimistically and demoted about 0.35 s earlier than at the gateway. Without the variable the queue is vLLM's unmodified one. Everything else is as in engine priority (B2TV): chat priority 0, documents priority 1, gateway pass-through with 64 in flight, `max_num_seqs` 16.

Configuration `B2TVE`. Four decisive cells (seed 7 mid45, seed 23 mid45, seed 11 mid42, seed 11 burst), 6 runs each, random order within repeat blocks, same SLOs, B2, `max_num_batched_tokens` 8192: 24 runs. Comparators (same traces): engine priority B2TV, chat-first + demotion B2TD, VD4.

## Hypotheses (decided before running)

Statistic: outcome design effect averaged over the 4 cells with a 95% run-level bootstrap interval, as in the previous studies.

- **E1 (the ordering decorrelates inside the engine queue):** DE(B2TVE) <= 1.0 (engine priority without ordering: 1.94).
- **E2 (no loss on chat, some gain on documents):** mean chat attainment >= 0.97 and mean doc attainment >= 0.92 (engine priority: 0.983 and 0.899).
- **E3 (robustness of passing):** B2TVE passes at least 3 of the 4 cells (chat >= 0.95 and doc >= 0.90; engine priority 2, chat-first + demotion 3).
- **E4 (miss count pinned):** the run-to-run SD of the number of document misses per run is smaller for B2TVE than for B2TV in at least 3 of the 4 cells.

If E1 fails, the statement that the demotion order is what decorrelates the outcomes is restricted to the gateway implementation and I report that. A new classifier (no prefix discount) is part of what is being tested; no parameter is tuned afterwards.

## Addendum: capacity ladder check for B2TVE (written after E1 to E4 were all met and before these runs)

E1 to E4 were all met on the four decisive cells (design effect 0.59, chat 0.983, doc 0.938, 4 of 4 cells passed, miss-count SD smaller in 4 of 4 cells). To see whether the configuration extends the capacity ladder, B2TVE is run at the heavier levels and at mid50 for seeds 7 and 23: cells seed 7 mid50, mid42, burst and seed 23 mid50, mid42, burst, 4 runs each (24 runs; seed 11 mid42 and burst already have 6). Pass rule as before (chat >= 0.95 and doc >= 0.90, mean over runs).

- **P1 (capacity gain):** B2TVE passes a strictly heavier level of the grid {mid50, mid45, mid42, burst} than any of gateway chat-first, chat-first + demotion and engine priority on at least 2 of the 3 seeds. (Already true on seed 7 at mid45, where the other three fail with 6 runs; seed 11 cannot be heavier because chat-first + demotion already passes burst, so it is a tie there at best.)
- **P2 (seed 23):** B2TVE passes mid42 (the other three fail it).
- **P3 (no harm at mid50):** on seeds 7 and 23, chat >= 0.95 and doc >= 0.90 at mid50.
- Whatever the outcome, the heaviest-pass levels are reported per seed; cells that fail are reported as failed.
