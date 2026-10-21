# CacheFlow: hypotheses and priorities

1. Under concurrent long-prefix bursts, a follower admitted after a producer's prefill/store can reuse KV and avoid duplicate prefill; bounded wait must cost less than the saved prefill time.
2. Under low prefix reuse, an age-aware bypass should keep gateway overhead and TTFT penalty small.
3. Under GPU cache pressure, LMCache CPU restores may help, but CPU-to-GPU transfer and host scheduling could erase gains. Measure both the hit and its cost.
4. If first-token timing does not predict store readiness, use a measured short grace or transparent fixed window; never call an inferred hit confirmed.

Deferred ideas: adaptive thresholds and alternative eviction only after B2/B3 causal comparison works. No kernel, quantization, training, or multi-GPU work in this sprint.
