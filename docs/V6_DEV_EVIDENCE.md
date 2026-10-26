# V6 development evidence: complete main matrix

The registered main matrix completed24measured runs: **1,440/1,440 requests, zero errors**, plus1,440separate warmups. It reuses60previously exposed QA over3arrival schedules, with a fresh vLLM+LMCache process per arm, identical warmup/reset, pinned Qwen3-4B,6GiB GPU KV, observed16,039,018,496byte host heaps, max native sequences16/graphs, preparation worker and uniform180s transport/keepalive0. This is development evidence, not a full1,986QA result, semantic holdout or long-service liveness proof. V5 and shared-process pilot results are separate protocols.

`results/v3/v6dev1_main_audit.json` verifies all24measured/24warmup ledgers, unique process units, exact source/config/actual factory argv, prompt/output/source tokens and official quality. `v6dev1_main_quality.json` contains per-question scores. The plot script reads only this complete audit; PNG/SVG were generated and visually inspected.

![Main-stack V6 development tradeoffs](../figures/v6dev1_main_tradeoffs.png)

Values below are arithmetic means of3run quantiles/counts. The QA population remains60, not180 per arm.

| Arm | TTFT p50 s | TTFT p95 s | Engine-consumed CPU KV tokens | New compute tokens | Answerable F1 |
| --- | ---: | ---: | ---: | ---: | ---: |
| FIFO16 | 25.060 | 35.891 | 918496 | 71810 | .313862 |
| FIFO64 | 25.065 | 35.877 | 918496 | 71810 | .313862 |
| Actual GPU LPM16 | 22.414 | 35.262 | 429082.7 | 69602 | .317511 |
| Bundle16 | 19.516 | 27.657 | 307888 | 67346 | .318357 |
| Fixed DHAS16 | 25.108 | 35.976 | 918496 | 71810 | .313862 |
| Original union64 | 15.320 | 19.696 | 75610.7 | 65676.7 | .316925 |
| Readiness-only FIFO64 | 24.944 | 35.731 | 918496 | 71810 | .313889 |
| Readiness+union64 | 15.535 | 19.383 | 76064 | 65602 | .316955 |

Readiness+union versus FIFO64 reduces mean-run p95 by45.973%, versus bundle by29.916%, and engine-consumed CPU-source tokens by91.719% versus FIFO. These are source-labelled token counts, not measured DMA bytes. Gate-only FIFO retains FIFO's compute/CPU-source work and nearly its latency: it does not explain the large gain. The primary evidence supports union/grouping under this memory-pressure regime.

The additional gate's improvement over original union is not established. Paired p95 changes across the3fresh-process schedule contrasts are **−1.662%, −3.982%, +1.078%**; p50 changes+1.958/−1.463/+3.863%. The exploratory paired-log-ratio t(df2) p95 descriptor is−1.544%, interval[−7.633,+4.947]%. It crosses0and rests on unverified n3independence/normality assumptions, so it is not a significance/population/quality-equivalence result. All three p99 differences favor readiness, but the analogous interval also crosses0. The original stall remains unexplained; no stall-fix claim follows from these successful fresh processes.

Quality F1 readiness−FIFO=.003093, readiness−bundle=−.001402, readiness−oldunion=.000030 on means. Against oldunion per-seed deltas change sign; each pair has4/60output hash differences. All arms have12output-cap hits per180scheduled responses across3seeds. Nearby means and equal cap-hit counts do not prove equivalent answers, and this dev cohort does not measure category5. The expanded native/main controls include separate abstention strata; full quality/category5still must be measured.

Completion p95 mean-run values FIFO64/bundle/oldunion/readiness are36.377/28.344/21.182/21.234s. Readiness therefore does not improve mean-run completion p95 over original union here. Client TPOT proxy p95 is19.263/55.195/110.799/93.580ms/token, respectively: union admission's TTFT gain coexists with a decode cost. This proxy is a per-request average after first text until response close, not individual native token ITL.

Supplemental native histograms have valid outside-window PID/prompt/generation/count/bucket coverage for22/24arms. FIFO16/FIFO64 seed101were explicitly skipped because observer registration was late; no retrospective values were invented. Means of valid per-run native update-interval means are FIFO64=19.516ms(n2), bundle=37.019ms(n3), oldunion=50.787ms(n3), readiness=45.786ms(n3). Native p95bucket bounds are FIFO64[10,25]ms(n2), bundle[50,75]ms, oldunion[150,200]or[200,300]ms, readiness[100,150]ms. These engine-update histograms corroborate a decode-distribution tradeoff but are not exact client token timestamps, and the unequal coverage must remain visible. Do not pool these observations with client TPOT or SGLang's differently weighted histogram semantics.

Per-conversation waits and actual head bypasses are retained in each audited run. New union/gate policies satisfy the observed bypass8bound; this does not imply a200ms admission/E2E deadline. The completed seed101old/newunion maximum admission waits are19.564/20.169s. Moving requests to frontend queues is included in scheduled-arrival TTFT; it cannot be hidden as an apparent engine TTFT improvement.

The native study has now prospectively registered60measured arms/2700requests and started SGLang, with18fresh blocks/1080separate warmups. Before its first registration, the plan was expanded from45arms to include originalunion in every native control; main controls similarly expanded from24to36arms1260requests2160warmups. No native results were used to choose that amendment. Full evaluation keeps both union policies, stronger native LPM/DFS/FIFO and mainFIFO/bundle. Current core/ablation conclusions remain conditional until native/controls/full and the final research requirement audit finish.
