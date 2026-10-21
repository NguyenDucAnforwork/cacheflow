# CacheFlow

Single-GPU study of delay-hit-aware admission for vLLM + LMCache CPU KV tier. The primary comparison is identical two-tier serving with FIFO (B2) versus a bounded-delay ingress scheduler (B3), using paired fixed-arrival traces and a low-locality negative control.

Current status and measured results: [docs/main_results.md](docs/main_results.md). Design decisions: [docs/decisions.md](docs/decisions.md). Reproduction log: [docs/reproduce.md](docs/reproduce.md).

This project is inspired by Strata's delay-hit problem; it does not reproduce Strata. No performance claim is made until experiments are complete.
