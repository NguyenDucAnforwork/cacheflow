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
