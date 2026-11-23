# Pre-registration (written before any policy-study run)

Question: between "medium" (0.9 s spacing of first document visits) and "burst" (0.4 s), does chat-first admission still
trade doc SLO for chat SLO, and does an age cap on queued docs help?

Setup: B2 (GPU + CPU KV tier), max_num_batched_tokens 8192, 60 chat + 14 docs (real60 traces), loads mid65 (0.65 s) and
mid50 (0.5 s) plus the existing medium/burst cells. Policies: FIFO, chat-first (`class_first`), chat-first with an age cap
(`class_aged`, a request that has waited >= 1500 ms since scheduled arrival is treated like chat; 1500 ms fixed before the
runs, not tuned). Two repeats per cell, order reversed on the second repeat.

- H-a: at mid65, chat-first gives chat SLO attainment >= 0.95 while doc stays >= 0.90 (no trade-off yet).
- H-b: at mid50, chat-first alone pushes doc below 0.90; the age cap keeps doc >= 0.90 with chat attainment at most 0.05
  below chat-first.
- H-c: for some load, no policy keeps both classes at target (chat >= 0.95, doc >= 0.90); there capacity, not order, is the limit.

Separate probe: isolated single-document prefill (no queue, no prefix hit) at max_num_batched_tokens 2048/4096/8192, to test
whether TTFT follows the number of scheduler steps beyond token count. Prediction: yes, ~ms per extra step, positive.
