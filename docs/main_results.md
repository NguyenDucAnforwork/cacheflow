# CacheFlow: live results

Status: implementation and initial paired experiments running. Results below are development measurements, not final holdout estimates.

## Host audit (2026-10-22)

| Item | Observed |
| --- | --- |
| GPU | GeForce RTX 3090, 24 GiB; idle at audit |
| CPU RAM | 247 GiB total, 183 GiB available at audit |
| Workspace disk | 20 GiB available initially; overlay filesystem |
| Workspace volume | false; sync code and results off-instance before recycle/destroy |
| Python / PyTorch | Python 3.12.3; torch 2.11.0+cu128 in /venv/main |
| vLLM / LMCache | not installed at audit |
| Git repository | absent at audit |

## Primary comparison

| Arm | Stack | Fixed-arrival result | CPU KV restore proof |
| --- | --- | --- | --- |
| B0 | vLLM, prefix cache off | measured below | N/A |
| B1 | vLLM, GPU prefix cache on, FIFO | measured below | N/A |
| B2 | B1 + LMCache CPU tier, FIFO | measured below | verified |
| B3 | B2 + DHAS gateway | two revisit pairs below | verified in revisit |
| B4 | B2 + static prefix grouping | one revisit screen below | verified in revisit |

The B2 CPU-restore smoke probe passed. B0, B1, B2 and B4 now have 8K revisit measurements below. The earlier B1 request pair was a functionality check.

Primary contrast is B3 vs B2 with identical engine, trace, model, token/output budgets, and cache pressure. Record arrival-based TTFT p50/p90/p99, TPOT, output tokens/s, requests/s, errors, GPU/host cache-hit tokens, CPU RAM, GPU memory/utilization, and scheduler queue wait. Report paired per-request deltas and repeat key conditions at least twice. A negative result is valid.

## Evidence gate

Do not label a request as CPU-restored from a prefix match alone. Require GPU-local eviction/absence plus LMCache L1 read or load counters and vLLM host-source cached token evidence if exposed by pinned versions. Missing metrics are marked not instrumented. Keep raw traces and exact Git SHA for every result.

## Setup checkpoint (2026-10-21 17:48 UTC)

Pinned stack installed: vLLM 0.22.0, LMCache 0.5.3, transformers 5.6.2, torch 2.11.0+cu128. Qwen3-1.7B revision `70d244cc86ccca08cf5af4e1e306ecf908b1ad5e` downloaded. B1 server booted and returned two 3,071-token prompt requests with 8 completion tokens each. After the second request, `vllm:prefix_cache_hits_total` was 3,056; this is a smoke check, not a benchmark result. LMCache MP HTTP/metrics server runs on localhost:18080; B2 connector verification is pending.

## Two-tier and gateway checkpoint (2026-10-21 17:56 UTC)

B2 MP connector booted and completed the CPU-restore probe after a local GPU prefix-cache reset. For the second 3,068-token request: LMCache L1 read +11 chunks, LMCache engine loaded +11 chunks, vLLM external prefix hits +2,816 tokens, and GPU-local prefix hits +0. This supports an actual CPU-tier restore. Raw response: `results/raw/restore_probe.json`. Gateway smoke replay completed 2/2 requests; client and vLLM both counted 4,492 prompt tokens. These are functionality checks, not B2-vs-B3 performance results. Supervisor now manages all three localhost services.

## Development screen: long-doc burst, no forced CPU restore (2026-10-21 18:03 UTC)

32 matched requests, 8,210–8,211 input tokens, 64 output tokens, same trace SHA `94d26c4d0049b9c91acdee9feae1f02ccfc2881e40dd93e6f0ab8e8646c2b576`. Cold B2 FIFO then cold B3 DHAS, one run each. B2 arrival TTFT p50/p90: 3,008/4,582 ms; output throughput: 216.5 tokens/s. B3: 2,906/4,485 ms; 218.7 tokens/s. All 32 output hashes match and all requests succeeded. B3 had 12 inferred delay-hit candidates. Gateway queue wait p50 rose from 1,389 to 1,417 ms. Both arms had exactly 196,608 GPU prefix-hit tokens and 66,128 new prefill KV tokens; neither recorded confirmed external KV loads. **This single AB-order screen does not support a cache-reuse claim or a robust speedup claim.** Repeat in balanced order and use a revisit trace for CPU pressure. Raw data and development figures are in `results/`.

## Development screen: long-document revisit with CPU restores (2026-10-21 18:11 UTC)

The deterministic revisit trace holds each document's last question until after other prefixes have pressured the GPU KV cache. It has 32 matched requests, 8,210–8,211 input tokens, 64 output tokens, and trace SHA `374cf57d2e2631eb5f1c8d605d2b25f453b0679925fe79f4c8989d26fda11781`. Each arm started with fresh B2/B3 services and cache state at Git SHA `cc1ae6536f8ad6cddfc0995fedf8b0ec4f4cffa4`.

| Pair and order | B2 TTFT p50/p90 ms | B3 TTFT p50/p90 ms | Paired mean B3−B2 ms | Output throughput B2/B3 tokens/s | B2/B3 external hit tokens | B2/B3 LMCache loaded chunks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| r1, B3→B2 | 1,426 / 3,954 | 1,808 / 4,408 | +302 | 186.9 / 185.8 | 65,536 / 58,960 | 256 / 231 |
| r2, B2→B3 | 1,754 / 4,253 | 1,805 / 4,288 | +31 | 185.3 / 186.2 | 65,536 / 65,536 | 256 / 256 |

All 128 requests succeeded and output hashes match within each pair. In both pairs, B2 and B3 had exactly 196,608 cached prompt tokens and 66,128 computed prefill KV tokens per arm. Thus the scheduler has **not reduced duplicate prefill** in this trace. Both arms show real CPU-tier reads and loads, but B3 does not consistently increase CPU restores. The large change in B2's timing between r1 and r2 means the magnitude of the TTFT penalty is unstable; request-level bootstrap intervals within one run do not capture run-to-run system variation. These two pairs do not support a DHAS performance win. Next: record negative-control and strong B0/B1 baselines, then repeat with a workload that stresses overlapping uncached producers while keeping matched arrivals.

### Why the 200 ms delay cannot work at 8K

The gateway trace audit found 10 delay-hit candidates in each revisit B3 run. Their matching producer's first token arrived a median 1,773 ms (r1) and 1,770 ms (r2) after the follower's scheduled arrival. **Zero of 20** producers reached first token within the 200 ms wait bound. Candidates waited about 200.5–200.6 ms at the gateway. The first-token signal therefore never released these followers early; their deadline did. This is a scheduler feasibility result, not proof about asynchronous KV-store completion. The older burst B3 screen had the same pattern: 12 candidates, zero producer first tokens inside 200 ms, median readiness delay 1,626 ms.

## Negative control: distinct 2K prefixes (2026-10-21 18:20 UTC)

32 requests per arm; trace SHA `839d484e1ef447e69c01971ab2e697748605392224c23cfc7fc2054bcbc5b020`; Git SHA `46fb90a212e4a90579c66a89e8127fec877d8fcb`. Order B2→B3→B3→B2, each cold restart. All 128 requests succeeded, and output hashes match within each pair. No request was marked a delay-hit candidate, and both arms had zero cached prompt tokens, zero GPU/external prefix hits, and 66,016 computed prefill KV tokens per run.

| Pair | B2 TTFT p50/p90 ms | B3 TTFT p50/p90 ms | Paired mean B3−B2 ms | B2/B3 output tokens/s |
| --- | ---: | ---: | ---: | ---: |
| r1 | 2,123 / 3,634 | 2,198 / 3,709 | +75 | 317.4 / 315.5 |
| r2 | 2,123 / 3,647 | 2,252 / 3,793 | +129 | 315.2 / 306.3 |

The no-reuse control does not meet a zero-overhead goal: B3 is slower in both runs despite no intentional deferral. vLLM queue-time sums rose from 9.18 to 9.82 seconds in r1 and from 8.94 to 10.04 seconds in r2; this is consistent with more host/engine contention but not enough to isolate the cause. More repetitions and GPU-clock/CPU process samples are planned. Request-level bootstrap intervals are not used as evidence for a run-level causal effect.

## Tier baselines: same 8K revisit trace (2026-10-21 18:28 UTC)

All runs share the 32-request trace SHA `374cf57d2e2631eb5f1c8d605d2b25f453b0679925fe79f4c8989d26fda11781`, 64 output tokens per request, cold service restarts, and the same GPU KV budget. All 160 requests succeeded. B0/B1/B2 benchmark summaries record Git HEAD `46fb90a212e4a90579c66a89e8127fec877d8fcb`; the B0/B1 launcher status handling was repaired locally before these replays and is included in the next commit. Serving engine and gateway policy code were unchanged.

| Arm/run | Arrival TTFT p50/p90 ms | Output tokens/s | Cached prompt tokens | Newly computed prefill tokens | Late revisit TTFT mean ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| B0 r1, no prefix cache | 10,653 / 14,686 | 77.9 | 0 | 262,736 | 13,666 |
| B1 r1, GPU prefix cache | 1,894 / 4,025 | 134.6 | 131,072 | 131,664 | 2,585 |
| B1 r2, GPU prefix cache | 2,017 / 4,100 | 135.2 | 131,072 | 131,664 | 2,598 |
| B2 r3, GPU + CPU tier | 1,541 / 4,054 | 183.9 | 196,608 | 66,128 | 334 |
| B2 r4, GPU + CPU tier | 1,452 / 3,980 | 182.9 | 196,608 | 66,128 | 373 |

B2 restored 65,536 prompt tokens from the external CPU tier in each measured B2 run, with 256 LMCache chunks loaded. The late revisit requests fell from about 2.59 s under B1 to 0.33–0.37 s under B2 (86–87% lower mean TTFT for that subset), while whole-run output throughput rose from ~135 to ~183 output tokens/s. B0→B1 establishes the much larger benefit of GPU prefix caching in this trace. These are development results from one host, not a universal speedup claim.

Output hashes were not perfectly stable across modes or repeated runs at temperature zero: each B1-vs-B2 pair had one mismatching request out of 32, and B0-vs-B1 had one. The deviations were on `doc-06-q2` in B2 r3, `doc-05-q3` in B1 r2, and `doc-02-q2` in B0 respectively; all still produced 64 output tokens. B2-vs-B3 pairs had zero output hash mismatches. The current runner stores hashes rather than the full generated text, so the materiality of those three deviations is not known.

## Static grouping control: 8K revisit (2026-10-21 18:33 UTC)

On the same trace and Git SHA `ac328da4af68e3e17aae892074b8c52d701a06ff`, B2 FIFO r5 had TTFT p50/p90 1,695/4,199 ms and output throughput 185.3 token/s; B4 static-group r1 had 1,709/4,284 ms and 186.3 token/s. Paired mean B4−B2 TTFT was +31 ms; all 32 outputs matched. Both arms had **identical** 196,608 cached prompt tokens, 66,128 computed prefill KV tokens, 65,536 external hit tokens, and 256 LMCache loaded chunks. Static grouping did not change cache reuse in this condition; one pair is only a screening result.

The new resource sampler reported B2/B4 GPU KV peak fractions 0.894/0.895, CPU L1 peak 7.0 GiB in both, VRAM peak 10,503 MiB in both, and minimum host available RAM 165.6/172.3 GiB. Mean sampled GPU utilization was 46.2/44.8%; these averages include idle samples and do not measure H2D transfer time. No memory-capacity or swapping problem was observed.

On the distinct-prefix 2K negative control at the same Git SHA, B2 FIFO r3 had TTFT p50/p90 2,291/3,805 ms and 307.3 output tokens/s; B4 static-group r1 had 2,424/3,971 ms and 300.3 output tokens/s. Paired mean B4−B2 TTFT was +133 ms with all 32 output hashes matching. Both had no cache hits. Grouping thus added latency where locality was absent in this one pair.

## Multi-turn sessions: 4K fit regime (2026-10-21 18:39 UTC)

The 32-request session trace SHA `1edc3c30f6f8b817d71dba092ff3bfde91a00d6b565ac005501966009c24266e` uses 4K target context and 64 output tokens, Git SHA `ac328da4af68e3e17aae892074b8c52d701a06ff`. B2 FIFO had arrival TTFT p50/p90 1,395/1,992 ms and throughput 401.9 output tokens/s; B3 DHAS had 1,437/1,978 ms and 400.9 output tokens/s. Paired mean B3−B2 TTFT was +27 ms. Both arms had exactly 98,432 cached prompt tokens, 33,680 computed prefill KV tokens, no external prefix hits, and no engine-loaded LMCache chunks. All requests succeeded, but **10/32 output hashes differed** between the two runs. No change in request input or output-token budget was detected; the runner only saved hashes, so the textual materiality of these deviations is unknown.

The B3 trace had nine inferred delay-hit candidates. Four matching producers emitted a first token within the 200 ms deferral bound, yet this did not increase cached-token reuse. First-token readiness may precede asynchronous KV-store visibility, or vLLM may have already shared these prefixes; the current metrics cannot distinguish those explanations. Do not infer a successful cache hit from a candidate count alone.

## Short 2K document burst: timing opportunity but no additional cache reuse (2026-10-21 18:42 UTC)

The matched 32-request trace SHA `32cadba96b7c4e29876338e6bfaf60cccabcd36990d7d405ec8f54cbf111029f` uses 2K document prefixes, 35 ms question spacing, 64 output tokens, and Git SHA `ac328da4af68e3e17aae892074b8c52d701a06ff`. B2 FIFO TTFT p50/p90 was 156/361 ms and output throughput 462.8 tokens/s; B3 DHAS was 213/523 ms and 457.2 tokens/s. Paired mean B3−B2 arrival TTFT was +82 ms. All requests succeeded; **4/32 output hashes differed**.

B3 marked 24 delay-hit candidates. A trace audit matched all 24 to a producer and found 18 producer first tokens inside the 200 ms bound. Despite the timing opportunity, both arms had exactly 49,152 cached prompt tokens and 16,976 computed prefill KV tokens, with no external CPU restores. vLLM's server-side TTFT sum fell from 5.36 s in B2 to 4.46 s in B3, but B3's arrival-based TTFT rose: gateway waiting moved time outside the engine metric without reducing actual prefill. The 2K result is a single development pair and does not establish a run-level effect magnitude.

## Simultaneous 8K siblings: first pair, mechanism still absent (2026-10-21 18:47 UTC)

The new trace schedules four sibling questions at the same millisecond for each of eight documents, retaining the exact prompt bytes from the earlier 8K burst. Trace SHA `d56acf0d02a03de0694b9701de6df8f628f7f2ffb6cc12ecbc1172ae4ce5589b`, Git SHA `58e6ea5cd1043e344678f5d378a4300c6167d756`. In the first B2→B3 pair, all 64 requests succeeded and all outputs matched. B2 TTFT p50/p90 was 2,884/4,472 ms; B3 was 2,639/4,218 ms, with paired mean B3−B2 −246 ms. Throughput was 221.5/227.9 output tokens/s.

Both arms again recorded exactly 196,608 cached prompt tokens and 66,128 computed prefill KV tokens; external CPU hits were zero. B3 had 12 inferred delay-hit candidates, all of whose producer first tokens came **after** the 200 ms bound (median 1,392 ms); each paid about 201 ms gateway wait. The apparent latency improvement has no measured reduction in duplicate prefill or increase in CPU restores.

The reverse-order B3→B2 pair also had all 64 requests succeed with 0 output hash mismatches. B3 TTFT p50/p90 was 2,584/4,176 ms versus B2 2,958/4,552 ms; paired mean B3−B2 −385 ms and throughput 229.0/219.8 output tokens/s. Cached and computed prefill token totals remained exactly the same as in pair r1. Phase decomposition in r1 gave B3−B2 arrival-to-dispatch −74 ms and dispatch-to-first −172 ms; in r2, −136 and −249 ms. Every one of the 32 requests shifted earlier in both pairs, including leaders, by a fairly uniform amount. The live-engine crossover below tested this possible run-level effect.

## Live-engine ABBA crossover resolves the apparent 8K win (2026-10-21 18:57 UTC)

The crossover used one vLLM PID `37744` and one LMCache PID `37591` throughout four runs in B2→B3→B3→B2 order, with the same 8K simultaneous trace and Git SHA `45145ac5047c24a85045d7fc37cb451f2d72a7d6`. Before each run, a fixed two-request direct-vLLM warmup was followed by LMCache L1 clear and vLLM GPU prefix reset. The first metrics sample of **all four** runs showed 0 L1 bytes and 0 GPU KV occupancy. The four arms all had exactly 196,608 cached prompt tokens, 66,128 computed prefill KV tokens, and zero external CPU hits. Each run succeeded 32/32; output hashes matched 32/32 within both pairs.

| Order pair | B2 TTFT p50/p90 ms | B3 TTFT p50/p90 ms | Paired mean B3−B2 ms | B2/B3 throughput tokens/s |
| --- | ---: | ---: | ---: | ---: |
| B2→B3 | 2,941 / 4,521 | 2,859 / 4,443 | −92 | 220.3 / 222.3 |
| B3→B2 | 2,730 / 4,308 | 2,850 / 4,431 | +109 | 225.9 / 222.6 |

The two run-level paired effects average about **+9 ms for B3**, with opposite signs. In the first pair B3's dispatch-to-first mean fell ~101 ms; in the reversed pair it differed by ~0 ms while arrival-to-dispatch rose ~109 ms. The large restart-based apparent win did not survive this stronger control. These data support a negative conclusion for **cache-based DHAS benefit** on this trace: prefill work was unchanged, and no reproducible arrival-TTFT gain is established. Request-level confidence intervals within one run would miss this run-level instability.

## Separate LMCache transfer-path profile (2026-10-21 19:00 UTC)

A single non-comparative B2 8K revisit replay used LMCache 0.5.3's OTLP tracing into a localhost sink. It completed 32/32 requests; it is excluded from latency comparisons because tracing changes the instrumentation path. `results/raw/otlp-profile.jsonl` contains 124 exported spans: 32 request roots, 32 lookup/prefetch spans, 52 store spans, and **8 retrieve spans**. The eight retrieves report 256 chunks and 7.0 GiB total, matching the external prefix hits and LMCache loaded-chunk counters. Each retrieve reported 896 MiB; span duration median/p90 was 149/157 ms (range 147–164 ms). This inclusive LMCache operation interval contains more than DMA and may overlap with other work, so it must not be presented as pure PCIe bandwidth or added directly to request TTFT. The pinned build did not export separate `transfer.staging` or `transfer.kernel_interval` spans; precise H2D and GPU staging times remain **not instrumented**. The 1-second CPU/GPU utilization plots are coarse overlap evidence only.

## Readiness-guard development crossover (2026-10-21 19:09 UTC)

One vLLM PID `41476` and LMCache PID `41336` served six 8K revisit runs in B3 original → B3 guarded → B2 FIFO → B2 FIFO → B3 guarded → B3 original order. The source SHA was `5280c743dc54a59e5f860f96af5e84c6bcdf05a4`, seed 7, common trace SHA `374cf57d2e2631eb5f1c8d605d2b25f453b0679925fe79f4c8989d26fda11781`. Fixed direct warmup and empty-cache reset preceded each run. All 192 requests succeeded. Every run reported 196,608 cached prompt tokens, 66,128 computed prefill tokens, 65,536 external hit tokens, and 256 LMCache chunks loaded. The guard did not create extra KV reuse.

| Run order | Policy | Arrival TTFT p50/p90 ms | Paired mean vs adjacent B2 ms | Guard bypasses |
| --- | --- | ---: | ---: | ---: |
| 1 | B3 original | 1,711 / 4,218 | — | 0/10 |
| 2 | B3 guarded | 1,354 / 3,848 | −211 (vs order 3) | 6/10 |
| 3 | B2 FIFO | 1,610 / 4,119 | reference | — |
| 4 | B2 FIFO | 1,727 / 4,315 | reference | — |
| 5 | B3 guarded | 1,753 / 4,247 | −3 (vs order 4) | 4/10 |
| 6 | B3 original | 1,491 / 4,028 | — | 0/10 |

Guarded-vs-original paired mean TTFT was −285 ms in the first bracket and +191 ms in the reversed bracket. The guard bypassed predicted-infeasible holds, reducing bypassed-candidate queue-wait median to ~20–21 ms from original DHAS candidate wait ~200.5 ms. Yet all observed matching producers reached first token later than the 200 ms bound, and the whole-run latency effect changed sign. One output hash differed in the first B2-vs-guard pair and none in the second; one differed in each guard-vs-original comparison. These development runs support a scheduler-wait mechanism, but **do not establish an end-to-end speedup**. An untouched seed 11 holdout is running with the frozen policy.

## Frozen-guard seed 11 holdout (2026-10-21 19:14 UTC)

The untouched `long_doc_revisit` seed 11 trace SHA is `fece35d29ada31e10d1b17d38789cc50970331759ff3f22a38eea6055d86087d`. Six 32-request runs used the frozen guard at source SHA `5280c74` in original B3 → guarded B3 → FIFO B2 → FIFO B2 → guarded B3 → original B3 order. vLLM PID `44375` and LMCache PID `44163` were unchanged. Each run began with 0 LMCache L1 bytes and 0 vLLM GPU KV occupancy after the same warmup/reset. All 192 requests succeeded.

| Order | Arm | TTFT p50/p90 ms | Paired mean guarded−comparator ms | Output hash mismatches vs guarded |
| --- | --- | ---: | ---: | ---: |
| 1→2 | B3 original → guarded | 1,504 / 4,037 → 1,609 / 4,246 | +111 | 3/32 |
| 3→2 | B2 FIFO → guarded | 1,652 / 4,156 → 1,609 / 4,246 | +3 | 3/32 |
| 4→5 | B2 FIFO → guarded | 1,554 / 4,054 → 1,696 / 4,188 | +98 | 2/32 |
| 6→5 | B3 original → guarded | 1,540 / 4,031 → 1,696 / 4,188 | +118 | 2/32 |

Each guard run marked 10 matching candidates and bypassed 4 predicted-late holds, with bypassed-candidate gateway wait p50 ~20.6–20.8 ms; no matching producer emitted first token inside 200 ms. All six arms cached 196,608 prompt tokens and computed 66,128 prefill KV tokens. The first guard arm used 59,072 external/137,536 GPU-local hit tokens and loaded 231 LMCache chunks; the other five used 65,536 external/131,072 local hits and loaded 256 chunks. Thus the total reuse was equal but one run changed its tier split. Five hash mismatches across the two FIFO-vs-guard pairs are logged; only hashes were retained, so content impact is unknown.

The frozen guard's two run-level effects versus FIFO are **+3 and +98 ms** (guard slower on average); versus original DHAS they are **+111 and +118 ms**. This holdout rejects the proposed latency improvement under this configuration, despite a real reduction in selected gateway waits. With only two run-level replicates, the exact penalty is uncertain. Request-level bootstrap intervals are not a substitute for additional independent runs.
