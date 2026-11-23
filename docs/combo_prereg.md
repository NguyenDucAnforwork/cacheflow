# Pre-registration: engine-level priority combined with doomed-document demotion

Written before any run of this experiment. Follows [robustness_mechanism_results.md](robustness_mechanism_results.md), which found that the best configuration depends on the document set: engine-level priority (B2TV) passes a heavier load level on seed 7, chat-first with doomed-document demotion (B2TD) on seeds 11 and 23, and the two were never combined.

## Design of the combination (`engine_demote`, config `B2TVD`)

The two mechanisms act in different queues, so they can be combined without changing vLLM:

- **Chat is never held at the gateway.** Chat requests bypass the gateway's in-flight cap and go straight to vLLM, where `--scheduling-policy priority` (chat priority 0, document priority 1, set by the client in the request body, as in B2TV) puts them ahead of any waiting document.
- **Documents are held at the gateway and admitted by demotion order.** At most 16 documents are in flight at once (the same cap as the gateway in the other configurations). Among queued documents, those that cannot meet their SLO even if admitted now (`waited + expected service > 3000 ms`, expected service = 150 ms on a recent prefix match else 72 ms per 1,000 prompt tokens, exactly as in B2TD) are served last; the rest are FIFO. Demoted documents are still served and stay in the denominator.

Because the engine's waiting queue then holds at most a few documents plus the chat requests, the "first queue where requests wait" for documents is the gateway (where demotion is applied) and for chat the engine (where priority is applied). The engine still runs at most 16 sequences. No parameter is new or tuned: SLO 3000 ms, 72 ms per 1,000 tokens and 150 ms are the values used in `class_demote`.

## Design

B2, `max_num_batched_tokens` 8192, 2 repeats per cell with reversed order on the second repeat. Config `B2TVD` at mid45, mid42 and burst on seeds 7, 11 and 23 (18 runs), plus mid50 on seed 7 (2 runs) as a no-harm check. The comparators B2TV and B2TD (and B2TP) at the same cells already exist (same traces; the code differs only by added policies). SLOs: chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms; pass = chat attainment >= 0.95 and doc >= 0.90, pooled over repeats and counted over all offered requests; heaviest pass on the grid {mid45, mid42, burst} requires a pass at every lighter level of that grid (a configuration that fails mid45 has no pass on the grid).

## Hypotheses (decided before running)

- **C1 (non-inferiority):** on every seed, B2TVD's heaviest pass on the grid is at least as heavy as the better of B2TV and B2TD.
- **C2 (gain):** on at least 2 of the 3 seeds, B2TVD's heaviest pass is strictly heavier than the better of B2TV and B2TD.
- **C3 (no harm at mid50, seed 7):** B2TVD is within 0.03 of B2TV (1.00 / 1.00) on both classes.
- **C4 (complementarity, descriptive with a threshold):** in every grid cell where B2TV misses the doc target and B2TD misses the chat target (or vice versa), B2TVD is within 0.03 of the *better* parent on each class. I will report the cells and the share that meet this.

If C2 fails, the combination is reported as no better than the best single mechanism, and the "best configuration depends on the document set" conclusion stands.

Not pre-registered: any explanation of why the combination does or does not help; the document will say so where it speculates.

## Addendum: attempt 1 did not bind; attempt 2 design (written before the attempt 2 runs)

**Attempt 1 (config `B2TVD`, 16 documents in flight) was run first and evaluated with C1 to C4:** C1 not met (seed 7: it fails mid45 where B2TV passes; seed 11: it passes mid42 but not burst where B2TD passes), C2 not met (0 of 3 seeds), C3 met at seed 7 mid50, C4 0 of 4 complementary cells. A diagnostic then showed that the design did not do what it was meant to: with only 42 document requests per trace, the document cap of 16 almost never bound, so documents had a gateway wait of 16 to 21 ms (same as B2TV) and all queueing happened in vLLM's FCFS-within-priority waiting queue, where demotion has no hook (document engine segment mean 1.2 to 2.4 s, against 0.34 to 0.43 s under B2TD). Attempt 1 is therefore effectively a second replicate of B2TV, not a test of the combination.

**Attempt 2** keeps everything except the document cap. The cap is set by a rule fixed from earlier data, not from the attempt 1 outcomes: the median over the 18 earlier B2TD runs (seeds 7, 11, 23 at mid45, mid42, burst) of the time-averaged number of documents in flight is 4.3, so the cap is **4** (config `B2TVD4`). This makes documents queue at the gateway, where the demotion order applies, while chat still bypasses the gateway and is ordered by the engine's priority. Cells, comparators, SLOs, pass rule, and hypotheses C1 to C4 are the same as above, evaluated for `B2TVD4`. It is a post hoc correction after seeing that attempt 1 failed to bind; the cap value rule is the only new choice, and it is not tuned on any B2TVD result. Both attempts are reported.
