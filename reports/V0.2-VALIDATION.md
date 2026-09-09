# Validation — standalone bring-up, 9 September 2026

## Current verified results

| Check | Result | Evidence |
|---|---|---|
| Standalone V8 CLI integration | **61/61 passed** | `standalone-tests.json`, `standalone-test-log.txt` |
| Python acquisition/input tools | **40/40 passed** | `python-test-log.txt` |
| Native scheduler | **12 checks passed**, CTest 1/1 | `scheduler-test-log.txt` |
| Separate Node development adapter | **55/55 applicable cases passed** | `test-results.json`, `development-test-log.txt` |
| Real V8 archive acquisition | ZIP + tarball SHA-256 verified | `acquisition.json`, dependency lock |
| Fresh offline Git clone/rebuild | Passed; repeated standalone + tool tests | `rebuild-validation.json` |
| Synthetic HAR -> immutable native probe | Passed; captured/executed body hashes equal | `synthetic-capture-probe.json` |
| Dynamic dependency audit | Standard system libraries only | `binary-audit.json` |

The standalone suite was run with Node's installation directory removed from
PATH. It starts a fresh native process for every case, including V8 initialization
and shutdown. It does not run the Node development adapter.

## Material change from the initial handoff

The standalone executable is now genuinely linked and running V8 13.6.233.17.
V8's matching generated ABI header is used, and a constructor compatibility
helper supports both tested V8 header APIs. The initial 47-case adapter-only
validation is preserved in `INITIAL-VALIDATION.md`; it is not current status.

The fixture suite covers absent globals, feature checks, script ordering,
microtasks, timers/cancellation, headless frames, error/rejection reports,
execution budgets, typed arrays, Unicode, diagnostic caps, and sync/async Wasm.
These are custom regression cases, not browser/ECMAScript conformance certification.

A new test exposed premature success for asynchronous WebAssembly: the old loop
returned `completed` without executing the callback. The fixed standalone loop
pumps V8 foreground tasks and observes actual Promise state via weak handles.
The synthetic Wasm function now returns **42**. Compile errors, unresolved
Promises, adopted pending Promises and observer capacity are tested. Incomplete
work is explicitly reported rather than silently counted as complete.

The Node adapter is not credited with Wasm support: its borrowed context rejects
Wasm code generation, and it has no standalone V8 default-platform pump.
Six engine-specific cases run only on standalone; the adapter report records
that boundary. No embedder restriction was disabled to manufacture a pass.

## Dependency acquisition and replay

The GitHub artifact-download connection supplied a standalone SDK when direct
container networking failed. Both archive digests match their published values.
`tools/bootstrap_v8.py` accepts the accompanying ZIP or the pinned release tar.gz,
checks both layers, rejects traversal/links/special files/duplicate entries, and
verifies an existing SDK before reuse. The complete offline acquisition/build
path was executed. The live release-download code path was not network-validated.

Original-game acquisition still produced **zero response bodies**. No parsed web
page or synthetic fixture was relabeled original Krunker code. Live script
capture and HAR import are tooling only. HAR tests include omitted bodies,
HTML challenge responses, disallowed origins, duplicate/conflicting data,
credential-header omission, byte hashes and honest text-vs-base64 fidelity labels.

## Not established

No original Krunker bundle or assets executed; no original-game dependency trace;
no native graphics/window/input/audio/network backend; no server session or
playability; no Windows/macOS validation; no performance improvement claim.
Headless animation callbacks do not render pixels. Promise observations introduce
diagnostic overhead and are not a finalized low-latency game-loop design.

The acquired SDK disables **V8 sandbox and ICU/Intl**. This is a development
bring-up dependency, not a hardened shipping configuration. A V8 context and
watchdog are not an OS security boundary. Independent SDK source rebuild,
production isolation/memory-limit validation, and a complete redistribution
notice audit remain open.

No Wok source, documentation or history was inspected. No remote GitHub repository
or fork was created or modified; the deliverables are the local source and Git
bundle, plus the acquired offline SDK.
