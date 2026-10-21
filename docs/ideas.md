# CacheFlow: hypotheses and priorities

1. Under concurrent long-prefix bursts, a follower admitted after a producer's prefill/store can reuse KV and avoid duplicate prefill; bounded wait must cost less than the saved prefill time.
2. Under low prefix reuse, an age-aware bypass should keep gateway overhead and TTFT penalty small.
3. Under GPU cache pressure, LMCache CPU restores may help, but CPU-to-GPU transfer and host scheduling could erase gains. Measure both the hit and its cost.
4. If first-token timing does not predict store readiness, use a measured short grace or transparent fixed window; never call an inferred hit confirmed.

Deferred ideas: adaptive thresholds and alternative eviction only after B2/B3 causal comparison works. No kernel, quantization, training, or multi-GPU work in this sprint.

## New testable question after first screen

Does bounded ingress deferral change engine scheduling latency even when it gains no extra cached KV, or is the approximately 100 ms improvement in one AB screen caused by warm-up/run order? Counterbalance B2/B3 and compare dispatch-to-first-token, queue wait, prefill KV tokens, and GPU activity. This is an interpretation question, not a new claimed contribution yet.

## Priority after two revisit pairs

The revisit trace confirms CPU-tier loads in both arms but no reduction in computed prefill KV tokens. Next test whether vLLM itself coalesces repeated prefixes before a 200 ms gateway delay could help. Use a shorter 2K prompt at low and moderate concurrency, record first-token time of the producer against the follower's deadline, and keep the negative distinct-prefix trace as a guard. If the producer cannot reach first token within the bound, label the delay-hit opportunity infeasible under the configured fairness bound rather than increasing the bound until a win appears.

Static grouping on the 8K revisit trace also left cache-hit and prefill-compute totals unchanged. A useful follow-up question is whether ingress scheduling has any room to improve once vLLM has already coalesced shared prefixes, or whether the best gateway decision is to bypass deferral for long-prefill groups. Compare a readiness-feasibility guard only after profiling and a 2K positive-locality screen, then evaluate it on an untouched seed.

The 2K burst showed many producer first tokens inside the 200 ms window, yet B2 and B3 each computed only about one full 2K document prefix per group and had identical cache totals. Next stress true simultaneous sibling arrivals at the same scheduled millisecond. This asks whether the 35 ms spacing already gave vLLM enough time to share in-flight prefix blocks; a simultaneous burst can expose redundant work if it exists. Keep prompt bytes and question IDs unchanged, alter only arrival offsets, and compare B2/B3 under the same new trace.

Even exact simultaneous 8K siblings did not create duplicate prefill under B2: vLLM cached three sibling prefixes per group and computed approximately one document prefix. The live-engine crossover then removed the apparent restart-based B3 win. A useful refinement target is therefore **harm avoidance**, not an invented cache speedup: use observed producer-first-token timing to skip a follower hold when readiness is unlikely inside the 200 ms bound. Test whether this reduces the clear 2K/8K revisit penalties without harming the already-fast FIFO behavior. Treat any result as a separate revised policy, not evidence that the original delay-hit hypothesis succeeded.
