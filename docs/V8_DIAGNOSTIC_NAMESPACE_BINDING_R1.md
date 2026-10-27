# V8 remaining-phase namespace binding correction

2026-10-27. V8diag2 registration/execution failed its preflight protocol hash
before any engine startup or request. The copied controller function had new
globals, but helper function objects still referenced their original module's
globals. Thus verify_pins read the V8diag1 protocol instead of the amendment;
probe_coverage would also have looked for the wrong journal prefix. The original
failure and source bytes remain unchanged under V8diag2.

V8diag3 fixes those two helper bindings in a new namespace. Unit tests execute
the actual rebound protocol verifier and journal-prefix coverage path. It keeps
the exact two unexecuted phases,on/offB, native hooks, model, full input, warmup,
600s timeouts, failed-engine post-replay accounting, uniform private engine logs
and cleanup defined in [the engine-exit amendment](V8_DIAGNOSTIC_ENGINE_EXIT_AMENDMENT.md).
That protocol remains an immutable dependency, pinned by this registration.
No offA retry, functional upstream patch or primary performance comparison.

The prospective registration additionally retains V8diag2 preflight failure
and pins the original amendment. CPU real-prefix verification is already
terminal/successful; its result hash and process absence are checked. All
remaining execution, source/model/native/input checks, strict coverage and
diagnostic-only claims remain those of the engine-exit amendment. No new
inference data was observed between V8diag2 registration and this correction.
