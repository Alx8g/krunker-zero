# Krunker Zero — 0.2 bring-up

**Delete the browser. Keep the JavaScript engine. Add host behavior only when evidence requires it.**

## What works now

A real **standalone Linux x86-64 executable** initializes V8, runs local classic
JavaScript unchanged, processes microtasks and native V8 engine tasks, and emits
structured diagnostics. This has been linked and executed without Node, Chromium,
Electron, CEF, a WebView, or a DOM library. No existing Krunker client was imported.

The native suite passes **61/61 integration cases**, including asynchronous
WebAssembly compiling and returning an actual value. Acquisition tools pass
**40 Python tests**, and the separate scheduler executable passes **12 checks**.
The optional Node development adapter passes **55/55 applicable cases**; it is
not used by the standalone binary and does not validate WebAssembly execution.

**Krunker itself has not been loaded.** No graphics, native mouse/keyboard, audio,
HTTP/WebSocket guest backend, or game assets exist yet. There is no playability
or speedup claim. The implemented browser-facing operations remain fixture-proven,
not an established minimum required by Krunker.

## Build and test without dependency networking

Use Python 3.10+, CMake 3.20+, a C++20 compiler, Linux x86-64, and the accompanying
`v8-13.6.233.17-linux-x64.zip`. No Node install is needed for these commands.

```sh
python3 tools/bootstrap_v8.py --archive ../v8-13.6.233.17-linux-x64.zip --build
python3 tools/test.py --host build/standalone/zero
build/standalone/zero --engine-info
build/standalone/zero --profile core fixtures/wasm-async.js
```

The dependency bootstrap verifies the outer ZIP and inner archive hashes, rejects
unsafe archive entries, installs matching V8 headers/library, then builds and runs
scheduler tests. Repeated setup verifies existing SDK files against the archive;
a changed SDK is rejected, not trusted from a receipt. An internet-connected
machine can substitute `--download` for `--archive` to fetch the pinned release.

Expected Wasm fixture log: `wasm 42`. This fixture is original test code, not game
code. To see the first absent host API in another synthetic fixture:

```sh
python3 tools/probe.py --host build/standalone/zero fixtures/needs-dom.js
```

This intentionally exits 2 with `missing_global: document`; it does not invent a
canvas or fake successful graphics calls.

## Important engine distinction

The acquired SDK contains V8 **13.6.233.17**, built by `kitten3d/v8-builds` from the
V8 subtree vendored in Node v24.20.0. **Node's runtime is not linked or launched.**
The final executable's dynamic dependencies are the ordinary C/C++ system libraries.
The dependency lock retains source/archive hashes, builder revision and artifact ID.

This particular SDK has **V8 sandbox and ICU/Intl disabled upstream**. It is an
experimental bring-up dependency, not a hardened shipping choice. There has been
no independent source rebuild, complete third-party redistribution audit, or
security assessment. Do not treat a V8 context or watchdog as an OS sandbox.
Production isolation and engine configuration remain separate acceptance gates.

## Acquire actual original inputs

On a machine with ordinary access to the original site:

```sh
python3 tools/capture.py --url https://krunker.io/ --out input/live
```

This saves the original HTML and explicitly discovered allowed-origin scripts,
not a browser implementation. It does not execute inline scripts or infer dynamic
loads. Additional asset origins require explicit `--allow-origin https://…`.
Denied requests, unsupported encodings, HTML returned for scripts, and missing
bodies are reported, never replaced with dummy JavaScript.

An authorized HAR export **with response contents** is the offline alternative:

```sh
python3 tools/capture.py --har /path/to/capture.har --url https://krunker.io/ --out input/imported
```

The importer omits cookies, authorization headers, POST bodies and unrelated
origins. URLs and script bodies may still contain secrets: keep `input/` private.
It distinguishes base64-decoded response bodies from text re-encoded as UTF-8;
text-mode HAR is not advertised as exact original network bytes. Contradictory
bodies for one URL are retained and flagged. Neither HAR network order nor HTML
tag order establishes script execution order.

Select and order the actual classic script inputs explicitly before `tools/probe.py`.
Do not run every captured advertisement or assume module scripts work as classics.
Inputs stay unchanged and outside Git. No authentication, anti-cheat or integrity
checks are bypassed.

## Runtime boundary

Default `bare` contains engine facilities only. The optional `core` profile adds
small console/timing bindings, cancellation, headless frame callbacks and
`window/self` aliases. It does not supply DOM/layout/canvas, WebGL, networking,
audio, input, storage, workers or module resolution.

The standalone host now pumps V8's foreground tasks and observes pending Promises
without replacing JS built-ins. Unsettled Promises produce a bounded incomplete
result, rather than a false completed result. This is conservative probe policy,
not browser liveness semantics; Promise tracking is diagnostic overhead.

See [runtime contract](docs/CONTRACT.md), [build details](docs/BUILD.md),
[next gates](docs/NEXT.md), and [validation](reports/VALIDATION.md).

The old development-only test route remains available:

```sh
python3 tools/test.py
```

It must never become the shipping runtime. No existing client repository, including
Wok, was read. This is still a local Git repository; no GitHub repository or remote
fork was created or modified.
