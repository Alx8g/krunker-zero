# Current runtime contract

This is deliberately a partial headless host, not a conforming browser.

## Bare profile

Fresh V8 context, engine-provided language facilities, no added host globals.
The debug console supplied by V8 is removed. No DOM, navigation, screen, storage,
network, graphics, audio, input, workers, URL loader or native module loader exists.
No arbitrary filesystem/process capability is made available to guest scripts.
Availability of V8's own Intl/WebAssembly facilities depends on the engine build;
this project has not established whether the game requires either.

## Core profile (explicit opt-in)

| Surface | Implemented contract | Intentionally not implemented |
| --- | --- | --- |
| `console.log/info/warn/error` | String conversion, structured bounded capture | Full DevTools object inspector, other console methods |
| `performance.now()` | Monotonic ms since the run started, or virtual scheduler time | Other Performance interfaces; `Date.now()` is not virtualized |
| `setTimeout/clearTimeout` | Function callbacks, delay coercion, extra arguments, cancellation | String-code handlers; HTML nested-timer clamping; background page policies |
| `setInterval/clearInterval` | Function callbacks, at least 1 ms cadence, cancellation including from inside callback | Catch-up storms or a full HTML event loop |
| `requestAnimationFrame/cancelAnimationFrame` | One-shot headless callbacks; same-batch timestamp; nested request deferred; same-batch cancellation works | GPU presentation, display synchronization, page-visibility behavior |
| `window`, `self` | Aliases to this guest global object | The Window interface and any of its unimplemented members |
| Promise jobs | V8 checkpoint after scripts, callbacks and pumped engine tasks | Browser event dispatch for error/unhandledrejection events |

Timers and animation callbacks are serviced by one native scheduler. Its simple
queue is intentionally unoptimized. Virtual-time execution is deterministic for
scheduler time only: it does not virtualize Date, randomness, JIT behavior or CPU
execution cost. Equal-due tasks have stable creation-order behavior.

Rejections unhandled at the end of a checkpoint fail the probe. A handler attached
within that checkpoint counts as handled. Attaching one from a later timer does
not rescue the run. This is a deliberate diagnostic policy, not a claim to reproduce
the browser's `unhandledrejection` notification/recovery behavior.

Default maximum pending callbacks: 4096. Default callback budget: 10000.
Default wall-clock budget: 2000 ms, including idle waiting. Source cap: 16 MiB per
input. Logs: 512 entries, each truncated at 4096 UTF-8 bytes with safe boundaries.
These are bring-up limits, not tested Krunker workload sizing.

The standalone probe pumps V8 foreground tasks nonblockingly on the isolate
thread. Weak Promise observations retain no guest Promise by themselves. Actual
Promise state is inspected after checkpoints: a resolve hook can adopt another
pending Promise, so a resolve event alone is not treated as settlement.

A still-reachable unresolved Promise keeps the diagnostic run alive only until its
wall-clock budget. With no host callbacks left, expiry is `async_work_timeout`;
an adapter with no engine task pump reports `async_work_pending` immediately.
This conservative policy can wait on intentionally idle Promises and is not a
browser event-loop liveness model. Asynchronous work hidden by guest exception
handling or unsupported API pathways still requires separate investigation.

The observation table is bounded at 65,536 live handles; settled/collected handles
are pruned at checkpoints and on capacity pressure. Overflow is an explicit
`promise_observation_limit` incomplete result. V8 engine task execution has its
own `max_tasks` budget, separate from the callback budget. These are diagnostic
limits, not benchmarked game settings. Promise hooks add instrumentation overhead.

The locked standalone build supports tested synchronous and asynchronous Wasm,
but omits Intl. No compatibility with untested engines is implied. There is no module graph/ES module host implementation. Dynamic
loading/imports and worker creation are not claimed to work.

## Graphics profile (compile-time and runtime opt-in)

`ZERO_BUILD_GRAPHICS=ON` plus `--profile graphics` enables the experimental native
EGL pbuffer surface and a real, small GL-shaped API. See [GRAPHICS.md](GRAPHICS.md)
for exact supported calls, caps, error behavior and deliberate omissions. This
profile still has no document, window presentation, input, audio or networking.
`bare` and `core` do not acquire these APIs merely because graphics is compiled.

Rendering is independent-fixture-tested, not current-game-tested. The native
renderer may itself be software (the observed device is llvmpipe). Presentation
counts remain zero. No complete WebGL, secure-shader-sandbox or hardware-latency
claim is made. Native driver calls cannot be preempted by the JS watchdog.

## Evidence rules

A fixture test verifies only that fixture's contract. An observed real-game trace
verifies only the branch/scenario reached for its recorded bundle hash. Missing
globals can be programming bugs as well as absent host APIs; examine the callsite.
Catching an exception inside the game can hide it from this first probe. Never
claim exhaustive API discovery, game compatibility or performance from one run.
