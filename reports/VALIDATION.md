# Validation — native graphics bring-up, 9 September 2026

## Verified results

| Check | Result | Evidence |
|---|---|---|
| Standalone V8 engine/timing/Wasm | **61/61 passed** | `standalone-tests.json`, `standalone-test-log.txt` |
| Actual native EGL graphics | **50/50 passed** | `graphics-tests.json`, `graphics-test-log.txt` |
| Broken-EGL fault injection | **2/2 passed** | `graphics-failure-tests.json` |
| Python acquisition/input/pixel tools | **63/63 passed** | `python-test-log.txt` |
| Native scheduler | **12 checks, CTest 1/1** | `scheduler-test-log.txt` |
| Separate Node development adapter | **55/55 applicable cases** | `test-results.json`, `development-test-log.txt` |
| Independent triangle's real framebuffer | **128x128 pixels verified** | `native-triangle.png`, `render-probe.json` |
| Minimal build excludes graphics | **passed** | `optional-graphics-boundary.json`, `minimal-binary-audit.json` |
| Enabled build's core profile loads no EGL | **passed** | `graphics-build-core-audit.json` |
| Actual graphics runtime library observation | **passed** | `binary-audit.json` |
| Real browser capture -> native round trip | **BLOCKED — NOT PASSED** | `capture-integration.json` |

These are independent contract fixtures, not game compatibility percentages or
WebGL/browser conformance certification. The optional graphics subset is not a
measured set of APIs required by Krunker. No actual game code has been executed.

## What changed

The host now optionally uses real EGL pbuffers and OpenGL ES shaders, programs,
buffers, uniforms, array/indexed drawing and RGBA8 readback. Native handles are
owned per context; JavaScript wrapper brands and cached intrinsics protect the
implemented native boundary from forged objects and simple prototype tampering.

Tests exercise actual pixel values, nonzero typed-array view offsets, upload
copying, native resource deletion, vertex/index bounds, stale uniforms, shader
and link failures, context switching, resize clearing and explicit caps. A buffer
cleanup defect was corrected: deletion now frees retained CPU shadow capacity,
not just its logical size. A regression checks the native reported capacity is
zero after repeated allocate/delete cycles. NUL-name and stale deleted-program
queries were also fixed and tested.

Missing library symbols and initialization failure are tested separately with
deliberately broken test libraries. They fail consistently on repeated attempts
instead of returning fabricated contexts or taking a partially initialized path.
These tests are not used as evidence of real rendering.

The PNG comes from the standalone fixture's readPixels output. The helper checks
native draw/compile/read counters, validates every row and stores hashes of the
fixture, executable, RGB bytes and PNG. No browser screenshot, image generator,
pre-rendered reference image or replacement game was used.

## Native driver and dependency boundary

Observed renderer: **llvmpipe (LLVM 19.1.7, 256 bits)**, reporting
**OpenGL ES 3.2 Mesa 25.0.7-2**. This is real native software rasterization, not
hardware GPU acceleration. The graphics report explicitly records **zero
presented frames**. There is no native window in this implementation.

The minimal/core observations have five system shared libraries and no graphics
library. The graphics observation has 41 runtime-loaded shared libraries, including
EGL, Mesa and LLVM. Neither path has an observed Node/browser library. Runtime
mapping is recorded because a direct-link-only audit would omit dlopen-loaded
graphics dependencies. This is one-fixture-path evidence, not a security or
minimum-footprint proof. Driver/system libraries are not bundled by this project.

## Actual acquisition status

The separate acquisition helper connects to a fresh local Chromium DevTools
endpoint. Its real localhost navigation fails with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. The integration result is `blocked`, exits
nonzero, and records **zero network bodies and zero compiled sources**. Browser
administration policy was not changed or bypassed. A helper unit test is not a
successful real-browser or real-game acquisition result.

The optional collector inventories permitted GET bodies and compiled inline/eval
source strings without patching game functions, hiding DevTools or capturing
cookies/auth headers/POST data. Network/body/source fidelity is explicitly
labelled; compiled snapshots are not blindly replayed as globals. It does not
capture workers, out-of-process iframes, fonts or every resource a full game needs.

The current original game bootstrap remains unavailable here. Parsed web-reader
homepage text and an outdated wrapper-modified archive were not substituted for
pristine executable game input. No current-game dependency trace exists.

## Still missing / not validated

Actual Krunker execution; native window and presentation; mouse/keyboard/pointer
lock; textures and image decoding; full relevant WebGL/GLSL validation; HUD/DOM or
its minimal measured replacement; audio; guest HTTP/WebSocket/TLS; asset-loading
lifecycle; real supported server sessions/reconnect; menus/settings/gameplay.
There is no complete-client, FPS, latency, size-reduction or speedup claim.

The SDK is unchanged: V8 **13.6.233.17**, with **V8 sandbox and ICU/Intl disabled**.
This is a bring-up configuration, not a secure shipping build. V8 contexts and
buffer checks are not OS isolation, diagnostic caps are not total memory limits,
and a JS watchdog cannot preempt a stalled driver call. Independent V8 rebuilding,
production hardening, complete redistribution notices, and Windows/macOS and
hardware-driver validation remain open.

No Wok code, documentation, history or implementation notes were inspected.
No remote repository, fork or deployment was created. First-party work remains
in the independent local Git history. `V0.2-VALIDATION.md` and
`INITIAL-VALIDATION.md` preserve earlier milestone descriptions.

The final offline reconstruction result is recorded in `rebuild-validation.json`;
its tested source commit identifies exactly which implementation was rebuilt.
