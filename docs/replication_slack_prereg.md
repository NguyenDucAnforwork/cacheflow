# Pre-registration: replication on a new seed, and a slack-based admission policy

Written before any run of these two experiments. Previous results: [policy_study_results.md](policy_study_results.md).

## Experiment 1: replication with new documents and chats (seed 11)

Same recipe as `real60` (14 QuALITY dev documents of 5.5K to 8.4K tokens, 60 ShareGPT first turns, same filters, same arrival profiles) but `--seed 11`, which draws a different set of documents and chats. B2, `max_num_batched_tokens` 8192, policies FIFO and chat-first, loads mid50 (0.5 s) and burst (0.4 s), 2 repeats per cell with reversed order on the second repeat (8 runs). SLOs as before: chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms.

- **R1** (mid50): chat-first keeps both classes on target (chat >= 0.95, doc >= 0.90), and FIFO misses the chat target (chat < 0.90), as with seed 7 (FIFO 0.68, chat-first 0.98 / 1.00).
- **R2** (burst): neither FIFO nor chat-first reaches both targets (as with seed 7: FIFO 0.30 / 0.88, chat-first 0.94 / 0.69).

If R1 or R2 fails, the earlier conclusion is reported as seed-dependent.

## Experiment 2: slack-based admission (`class_slack`)

Policy: chat first (FIFO within class). A doc is treated like chat once its remaining slack is smaller than its expected service time plus a margin: promote when `waited >= doc_slo - est_service - margin`, with `doc_slo` = 3000 ms (the SLO), `est_service` = 72 ms per 1,000 prompt tokens (from the isolated probe), `margin` = 500 ms (a fixed allowance for engine contention; chosen before the runs and not tuned). For a 7K-token doc this promotes at about 2.0 s of waiting. Seed-7 traces (`real60`), B2, 8192.

New load `mid45` (first visits every 0.45 s) between mid50 and burst. Cells: mid45 x {FIFO, chat-first, class_slack}; mid50 and burst x class_slack (new); 2 repeats each, reversed order on the second repeat (10 runs). Existing FIFO and chat-first cells at mid50 and burst are reused (same traces, same code path).

- **S1** (mid45): chat-first or FIFO misses at least one target, and class_slack reaches both (chat >= 0.95, doc >= 0.90). Otherwise the result is "no window for a slack policy at this load".
- **S2** (mid50): class_slack stays within 0.03 of chat-first's chat attainment and keeps doc >= 0.90 (it must not give up the free case).
- **S3** (burst): class_slack does not reach both targets (capacity-limited).

I do not know beforehand whether mid45 lies inside a feasible window; a null result there is a result.
