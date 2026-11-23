# Pre-registration: SLO-constrained capacity by configuration, and engine-level priority

Written before any run of this experiment. Context: the previous studies compared policies at a few loads; this one adds the measurement that makes them comparable (SLOs-Serve defines "serving capacity" as the maximum load that still keeps 90% SLO attainment) and tests where the priority ordering is implemented.

## Part A: capacity ladder

**Definition.** A configuration *passes* a load level when, pooled over its repeats, chat SLO attainment >= 0.95 and doc SLO attainment >= 0.90 (SLOs: chat TTFT <= 1 s, doc <= 3 s, TPOT <= 100 ms; attainment over all offered requests). Load levels are the existing arrival profiles ordered by first-visit spacing: medium (900 ms), mid65 (650), mid50 (500), mid45 (450), burst (400); offered load is reported as total requests per second of the trace span. A configuration's **capacity bracket** is (heaviest level where it passes and every lighter tested level also passes, first level above it that fails). No interpolation between levels.

**Configurations** (B1 = GPU prefix cache only; B2 = GPU + CPU KV tier; 2048 / 8192 = `max_num_batched_tokens`): B1 2048 FIFO; B2 2048 FIFO; B2 8192 FIFO; B2 8192 chat-first; B2 8192 chat-first + doomed-document demotion. (Existing cells are reused; new runs fill the missing cells: seed 7: B1 at medium/mid65/mid50/mid45, B2 2048 at mid65/mid50/mid45; seed 11: B2 8192 FIFO, chat-first and demotion at mid45, B1 and B2 2048 at mid50 and mid45.) Two repeats per cell.

- **K1:** on both seeds (7 and 11) the capacity ordering is B1 <= B2 2048 <= B2 8192 FIFO <= {chat-first, demotion} (a later configuration never has a lighter bracket than an earlier one).
- **K2:** on each seed, B2 (2048, FIFO) passes at least one load level heavier than B1's heaviest pass (the CPU tier raises capacity).
- **K3:** on each seed, the best of {chat-first, demotion} passes at least one load level heavier than B2 2048 FIFO (the larger prefill budget plus class ordering raises capacity).

If K1 fails on a seed, the ordering is reported as not stable.

## Part B: where the priority ordering lives

Compare gateway-level chat-first (existing policy `class_first`, 16 in-flight slots) with engine-level priority: vLLM `--scheduling-policy priority`, requests carry `priority` 0 (chat) or 1 (doc), the gateway admits up to 64 in-flight (FIFO, effectively a pass-through) so queueing happens in vLLM's waiting queue (vLLM keeps `max_num_seqs` 16). 8192, B2.

- **V1:** engine-level priority matches gateway chat-first within 0.03 on both classes' SLO attainment at seed 7 (mid50, mid45, burst) and seed 11 (burst).
- **V2 (descriptive):** chat gateway wait is near zero under engine priority (the queue moved into the engine); report chat/doc TTFT percentiles and goodput.

Cells: seed 7 mid50, mid45, burst; seed 11 burst; 2 repeats each (8 runs).

## Part C: real arrival structure (BurstGPT)

Written before building the traces or running them. Source: `BurstGPT_1.csv` (HPMLL/BurstGPT; Azure OpenAI GPT service trace; integer-second timestamps, request/response token counts, no text). Two windows (window seeds 1 and 2) of 74 consecutive 'Conversation log' requests; timestamps jittered uniformly inside their second, rescaled to a 10 s span; the 14 longest requests (by `Request tokens`) become the document first visits, the other 60 are chats; document and chat content copied from the seed-7 `real60` trace; q1 = q0 + 1.3 s, q2 = q0 + 8 s. The load level is not matched to any earlier profile (it depends on the window), so this is a check on arrival structure, not a capacity measurement. Policies: FIFO, gateway chat-first, chat-first + demotion; B2 8192; 2 repeats per cell (12 runs).

- **G1:** in each window where FIFO misses the chat target (chat SLO < 0.95), chat-first raises chat SLO by at least 0.20.
- **G2:** in each window, demotion keeps chat SLO within 0.05 of chat-first and has doc SLO at least equal to chat-first's.
- If FIFO passes both targets in a window, that window carries no information about G1 and is reported as such.

## Addendum (written after seeing the first engine-priority results, before the control runs)

Seed 7 engine priority (B2TV) came out better than gateway chat-first: mid45 chat 0.99 / doc 0.92 (chat-first 0.94 / 0.83), burst 0.98 / 0.71 (0.94 / 0.69), mid50 1.00 / 1.00 (0.98 / 1.00), against hypothesis V1 (within 0.03); V1 holds only at mid50 and at seed 11 burst. B2TV differs from gateway chat-first in two ways: engine-side ordering and a wider gateway (64 in-flight instead of 16). Control runs (not pre-registered as hypotheses; added after the fact to separate the two): gateway FIFO with 64 in-flight and no engine priority (`B2TW`) and gateway chat-first with 64 in-flight (`B2TPW`), seed 7 at mid45 and burst, 2 repeats each (8 runs). Reading rule fixed now: if B2TPW matches B2TV (within 0.03 on both classes), the gain came from the wider gateway, not from engine-side priority; if B2TV stays better on both classes by more than 0.03, engine-side ordering contributes.
