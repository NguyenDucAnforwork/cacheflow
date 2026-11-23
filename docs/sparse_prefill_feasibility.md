# Sparse prefill: feasibility check (no experiment run)

A time-boxed check (about 15 minutes of web research, nothing installed or run) of whether a sparse-attention prefill method could be tried on this setup: vLLM 0.22.0 with chunked prefill, Qwen3-1.7B, one RTX 3090 (sm86), documents of 6 to 8K tokens. **Verdict: not feasible as a quick experiment, and unlikely to matter at these prompt lengths.** What I did not do: measure anything. The statements about prompt-length benefit are from the papers' own evaluations, not from this host.

## Candidates and why each does not fit

| Method | What the sources say | Obstacle here |
|---|---|---|
| UniPrefill ([arXiv 2605.06221](https://arxiv.org/abs/2605.06221), code at [github.com/qhfan/UniPrefill](https://github.com/qhfan/UniPrefill)) | Block-wise dynamic sparsification implemented as fused Triton kernels; the repository is built on a bundled **vLLM v0.16.0** with model integrations for **Llama 3.1, Qwen3-Next and Gemma3**, plus changes to the FlashAttention backend | Different vLLM version than the pinned 0.22.0; Qwen3-1.7B is not among the integrated models; would need a port, not a configuration change |
| MInference ([project page](https://www.microsoft.com/en-us/research/project/minference-million-tokens-prompt-inference-for-long-context-llms/), [PyPI](https://pypi.org/project/minference/)) | Training-free dynamic sparse attention for prefill; the vLLM path is documented for vLLM >= 0.4.1 by wrapping the `LLM` object, **with chunked prefill disabled**; evaluated on A100 and long contexts (LLaMA-3-1M, GLM-4-1M, Yi-200K, Phi-3-128K, Qwen2-128K) | This stack uses vLLM's V1 engine with chunked prefill (which the study depends on); Qwen3 is not named among the evaluated models; no result for RTX 30-series |
| BFLA ([arXiv 2605.12193](https://arxiv.org/abs/2605.12193)) | Training-free block-filtered attention, evaluated on Gemma 4, Llama 3.1, Qwen 3.5 and 3.6, with a reported 2.5x speedup on Qwen 3.6-27B at 128K tokens | I found no public code |
| FlashPrefill V2 ([arXiv 2608.19758](https://arxiv.org/abs/2608.19758)) | Block-sparse prefill attention built around a paged KV cache, described as usable as an attention backend in serving engines | Compatibility with vLLM 0.22.0, Qwen3-1.7B and sm86 not verified; I did not find a ready integration |

## Why the benefit is doubtful at 6 to 8K tokens (an estimate, not a measurement)

The reported speedups are at 128K tokens and beyond, where attention dominates prefill time. At 6 to 8K tokens the isolated probe in this project measured about 72 ms per 1,000 prompt tokens for the whole prefill, and the part due to attention was not separated. A rough estimate (attention share of prefill FLOPs at 8K for a hidden size of 2,048) suggests it is not negligible, so the premise that sparse attention cannot help at 8K is not safe either; but any gain would be bounded by that share and would carry an accuracy risk on QuALITY (answers need information from the whole document), which would have to be measured.

## What it would take

Roughly 3 to 5 hours: port one of the methods (most likely UniPrefill's operator) to vLLM 0.22.0 and Qwen3-1.7B or run it on its pinned vLLM 0.16.0 with a model it supports, verify it runs on sm86, measure speed on the isolated probe first (6 to 8K tokens), then measure QuALITY accuracy with the sparse setting, then only if both are acceptable run it through the serving experiments. Chunked prefill compatibility (used throughout) is the main unknown.

## Position in the project

Listed as a next step in the README (section 13, item 5). The more promising items for the capacity question are those that act on admission and scheduling, which is where this project found its effects; sparse prefill acts on per-request compute and would show up as a shift of the ladder only if prefill compute is the bottleneck at the saturation points studied here.
