# Krunker Zero

**Delete the browser. Keep the JavaScript engine. Add host behavior only when evidence requires it.**

A new, independent native-runtime experiment. No Chromium, Electron, CEF, WebView,
HTML layout engine, DOM library, or existing Krunker client implementation is used
by the standalone target.

## Status: foundation, not a playable client

The repository contains an implemented C++ V8 host, a native scheduler, optional
small timing bindings, input-hashing tools, and automated tests. The standalone
entry point compiles against the available V8 headers. The same native bindings
have been executed using a **development-only Node/V8 test adapter**.

**The standalone executable has NOT been linked or run here. Krunker itself has
NOT been loaded. There is no graphics, input, audio, HTTP, or WebSocket backend yet.
There are no measured FPS, memory, size, or input-latency improvements.**

The build environment has Node/V8 headers but no standalone V8 archive and cannot
download dependencies. This limitation is recorded rather than hidden behind a
Node-based shipping client. Nothing in `native/node_smoke.cc` or
`tools/smoke_driver.cjs` belongs in the shipped runtime.

## What is actually implemented

`native/main.cc` initializes standalone V8 and evaluates explicitly supplied local
classic scripts, in order. `native/host.cc` runs them in a fresh context, drains a
private microtask queue, and reports failures as JSON. The game gets no filesystem,
process, shell, module loader, or networking API from this host.

The **bare profile**, which is the default, does not install browser globals. V8's
built-in debug console is explicitly removed so it cannot hide a missing host API.
The engine's own language features remain; this is not a JavaScript interpreter
written from scratch.

The optional **core profile** adds bounded console capture, `performance.now`,
function-only timers, cancellable headless animation callbacks, and two global
aliases (`window` and `self`). They are fixture-tested support functions, **not
an assertion that the current game needs every one of them**. They are opt-in.

Animation callbacks use a synthetic/headless cadence. No GPU frame is presented.
`--virtual-time` skips waiting and must never be used as an FPS benchmark.

## Run the tests

On Linux, with Python 3, CMake, a C++20 compiler, and installed Node headers:

```sh
python3 tools/test.py
```

This builds/runs the native scheduler tests, tests the Python input tools, compiles
the standalone CLI to an object, and runs the native V8 integration cases through
the explicitly labeled development adapter. No npm install is involved.

For scheduler-only testing, with no Node or V8 dependency:

```sh
cmake -S . -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native
ctest --test-dir build/native --output-on-failure
```

## Observe a real failure, without faking the missing API

```sh
python3 tools/probe.py --dev-node-smoke fixtures/needs-dom.js
```

This synthetic fixture attempts `document.createElement('canvas')`. It exits 2 and
reports `missing_global: document`. That is an expected test result, not a game
compatibility failure observed in the current Krunker bundle.

```sh
python3 tools/probe.py --dev-node-smoke --profile core --virtual-time fixtures/clock.js
```

This tests script execution, Promise ordering, one timer and one headless animation
callback. It does not render anything.

## Run original game inputs once the standalone host is built

Build instructions are in `docs/BUILD.md`. Keep authorized, original inputs under
`input/`, which is ignored by Git. Do not add proprietary game code to this repo.

```sh
python3 tools/probe.py --host build/standalone/zero input/game.js
# If the original page needs several classic scripts, supply their proven order:
python3 tools/probe.py --host build/standalone/zero input/vendor.js input/game.js
```

The probe hashes the exact input bytes and runs unchanged snapshots. It does not
rewrite code, inject bypasses, download hidden bundles, or guess script order.
`tools/inspect_bootstrap.py` can inventory script tags from locally saved original
HTML; that is markup evidence, not a faithful replay of async/module loading.

## The implementation loop

1. Run an identified original input with an explicit version/hash.
2. Record the actual failing operation and the scenario that reached it.
3. Reduce it to a small independent regression fixture.
4. Implement the required semantics, including relevant errors and ordering.
5. Rerun that scenario and retain the fixture before moving to the next failure.

Do not create a universal proxy that returns fake objects for unknown APIs. Do not
silently ignore calls. Do not remove validation merely to reach the next line.
A completed script means that one execution ended; it does **not** prove that a
match, UI, settings flow, reconnect, or different map works.

See `docs/DESIGN.md` for the graphics/UI decision points, `docs/CONTRACT.md` for
intentional limitations, `docs/NEXT.md` for the next acceptance gates, and
`reports/VALIDATION.md` for exactly what was verified.
