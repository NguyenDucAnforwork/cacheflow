# V9 native intervention: host-metadata preflight correction

2026-10-27. Original V9repair1 remains failed/incomplete. Its reference warmup
completed60/60requests and verified actual native WORKER/SCHEDULER constructor
code fingerprints. The first target was never sent: controller-created
`RUN_ID.host_status.json` violated the collector's broad `RUN_ID.*` freshness
check. The per-engine log also used the protected raw prefix; that second
collision was found in preflight review before this new registration. The
original failure,60warm outputs and constructor proofs stay intact.

V9repair2 is an explicit new attempt after that integration correction, retaining
all six modes/seeds/order/inputs/settings/gates/audits of
[the original intervention](V9_NATIVE_WATERMARK_INTERVENTION.md). It uses a fresh
engine and separate60warmups for every arm; no old warmup or output is stitched
into a new run. All input QA were already exposed. This is not an implicit
request retry or a primary performance study.

Only experiment namespace and owned startup-metadata filenames change: the
snapshot is `RUN_ID-host-status.json` and log is `RUN_ID-engine.log`, outside the
collector's protected raw/setup prefixes. The stopped engine log SHA is audited.
Freshness guards remain strict; actual run artifacts still reject reuse.
The corrected auditor expects that filename. A direct preflight test creates
the real controller filename, executes the actual transformed collector up to
the first mocked health check, and checks that a genuine prior run artifact is
still rejected. This exercises the integration missed by the original mocks.

The new registration pins the original registration/failure/warm evidence,
original protocol, unchanged original source/native bytes, corrected actors and
this amendment. Native hook, one-statement watermark change, effective-code
fingerprints, role checks, quality scoring and all failure/cleanup/probe gates
are unchanged. Zero idempotent-mode GPU requests occurred before this correction.
The original contribution/strong-baseline/full-confirmation requirements remain.
