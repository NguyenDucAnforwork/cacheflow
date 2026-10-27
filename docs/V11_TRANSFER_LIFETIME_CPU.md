# V11: conditional async-transfer lifetime evidence

2026-10-27. This is an executed CPU mechanism experiment, not a serving revision,
GPU result, diagnosed cause of the earlier stall or completed contribution.
V9 and queued V10 serving sources, protocols and registrations remain unchanged.

## Observed failure and question

The full V9 idempotent901 run retained925successes/1061errors. Its EngineCore
traceback maps to installed Scheduler._update_from_kv_xfer_finished line2153,
inside finished_recving. The preceding598.066s sampled nonprogress is separate
evidence. The missing request ID, its cancellation history and worker future
state at failure were not logged. Could the installed complete method bodies
produce this assertion under an explicit cancellation/completion order?

## Executed native-body witness

`v11_transfer_lifetime_witness.py` compiles selected complete installed bodies
without importing vLLM/torch/CUDA. Decorators are omitted and annotations deferred;
RequestStatus is compiled from its actual enum body. The selected methods are
Scheduler.finish_requests/_free_request/_free_blocks/_connector_finished/
_update_from_kv_xfer_finished, LMCacheMPConnector.request_finished and worker
get_finished/_process_finished_stores/_update_and_get_finished_store. Queues,
request objects, block-free callbacks and future readiness/results are fixtures.
All transfers are assumed registered before terminal delivery, and IDs unique.

The native scheduler initially retains the aborted WAITING_FOR_REMOTE_KVS request.
Subsequent native worker acknowledgements can release it before another registered
operation completes, or release it twice. Each order is tested with terminal
input sent once and repeatedly, yielding8conditional cases:

| Fixture order | Native result | Transfer still pending at first free callback? |
| --- | --- | --- |
| No STORE; terminal ack before RECEIVE completes | Later receive-loop assertion2153 | Yes, retrieve |
| STORE completes before RECEIVE | Later receive-loop assertion2153 | Yes, retrieve |
| RECEIVE completes before STORE | Later send-loop assertion2162 | Yes, store |
| Both complete in the same report | Receive frees, then send-loop assertion2162 | No; duplicate release notification |

A positive control receives while nonterminal, then cancels, and releases once
without assertion. This proves only the declared metadata interleavings are
accepted by these selected native bodies; it does not establish live reachability
or pending DMA. A not-ready dummy future is not a measured GPU event.

The initial scaffold selected the non-HMA _connector_finished fallback. The real
connector declares SupportsHMA. `v11_hma_transfer_control.py` therefore explicitly
binds the HMA dispatch and actual request_finished_all_groups body, then executes
the same8cases and16barrier controls. Original scaffold/source/artifact bytes
remain retained. This supplement uses one KV group of dummy IDs; arbitrary
hybrid-attention layouts and actual connector construction are not reproduced.

## Unactivated barrier control

`TerminalTransferBarrier` is a standalone prototype with no hook/entrypoint.
It calls the native completion collector exactly once, adds no future query,
result wait or event synchronization, and tracks terminal IDs separately. For
terminal requests it withholds both native acknowledgements while a registered
retrieve/store future remains, then emits one finished_sending. Nonterminal
finished_recving remains unchanged. This avoids the premature/double release
callbacks in the declared fixture, without deleting a scheduler assertion.

Sixteen controls per dispatch scaffold cover four operation orders, once/repeated
terminal signals and healthy/unhealthy native draining. Failed native operations
stay failures/error blocks; unhealthy draining is not successful DMA quiescence.
The prototype rejects transfers registered after its terminal acknowledgement.
Its tombstones grow without bound, IDs cannot be reused, and late/unseen operation
registration has not been resolved in a real asynchronous engine. No production
allocator/tensor correctness, liveness, fairness, output quality or performance
claim follows. Do not activate this prototype in V9/V10.

## Prior work checked before any novelty claim

[LMCache issue5937](https://github.com/LMCache/LMCache/issues/5937), opened
2026-10-21, reports abort/retrieve completion ordering on a newer stack and a
send-loop crash. Our observed receive-loop frame and conditional orders must not
be silently identified with that report.

[PR5938](https://github.com/LMCache/LMCache/pull/5938) proposes carrying scheduler
knowledge of retrieves that finished while loading to suppress a later send
notification. [PR4939](https://github.com/LMCache/LMCache/pull/4939) proposes a
broader loading lifecycle. Both were open/unmerged at the recorded API check;
exact head/base SHAs and timestamps are in `v11_transfer_prior_art.json`.
Neither PR was ported or executed here. These establish relevant prior work,
not proof that a particular patch fixes our initial stall. This work does not
claim the general abort/completion bug family or lifecycle idea as novel.

## Reproduction and remaining evidence

```bash
PYTHONPATH=src:scripts /venv/main/bin/python -m pytest -q tests/test_v11_transfer_lifetime.py
```

The three result JSONs preserve native/method/source hashes, each declared order,
assertion site, query counts and control outcomes. Output scripts use exclusive
creation; use a new path to rerun and preserve the first evidence. Native library
files are never written. Before a serving intervention, capture the actual
request/future/terminal chronology around a qualifying stall without extra
future polls, determine operation-registration ownership/fencing, and compare
with an explicitly pinned appropriate upstream correction. Existing V9/V10
measurements continue under their unchanged registrations. Epoch GPU, matched
controls and full three-seed bundle/DFS evidence remain required for the original
research objective, independently of this correctness investigation.
