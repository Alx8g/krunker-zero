# Krunker Zero — 0.3 native graphics bring-up

**Delete the browser. Keep the JavaScript engine. Add only evidenced host behavior.**

## Current result

A standalone Linux x86-64 V8 host now executes real shaders, uploads vertex/index
buffers, draws triangles and reads back their pixels through native EGL/OpenGL ES.
The optional graphics target contains no Chromium, Electron, Node or DOM library.
The default build still excludes graphics entirely.

**Krunker itself is not running.** No current original game bootstrap has been
acquired or executed. The triangle is independent test code, not a game frame.
There is no window presentation, mouse/keyboard integration, audio, guest network
stack, complete WebGL implementation, server session, or measured speedup.

The actual renderer observed here is Mesa **llvmpipe**, a software renderer. The
code calls real EGL/GLES; this is not a mocked renderer or proof of hardware GPU
performance. See [the rendered pixels](reports/native-triangle.png) and their
[execution/readback report](reports/render-probe.json).

## Offline build and run

Requires Linux x86-64, Python 3.10+, Git, CMake 3.20+, a C++20 compiler and the
accompanying `v8-13.6.233.17-linux-x64.zip`. Graphics additionally needs a working
system EGL/GLES driver supporting surfaceless pbuffers. No graphics development
headers, Node or browser are needed to compile or execute the native host.

```sh
# Verify and install the matching V8 SDK, then build the minimal host.
python3 tools/bootstrap_v8.py --archive ../v8-13.6.233.17-linux-x64.zip --build

# Opt in to the experimental native renderer.
cmake -S . -B build/standalone -DZERO_BUILD_GRAPHICS=ON
cmake --build build/standalone -j2

# Test the host and actual graphics operations, then write the framebuffer PNG.
python3 tools/test.py --host build/standalone/zero
python3 tools/test_graphics.py --host build/standalone/zero
python3 tools/test_graphics_failures.py --host build/standalone/zero
python3 tools/render_probe.py --host build/standalone/zero
```

`render_probe.py` runs the supplied JavaScript fixture and encodes its verified
readback bytes as PNG with Python's standard library. It does not generate an
illustration, use a browser screenshot or substitute a reference image.

A system without an appropriate EGL driver gets an explicit failure. No fallback
browser is launched. `-DZERO_BUILD_GRAPHICS=OFF` removes the graphics profile; in
both builds the `bare` and `core` profiles leave `OffscreenCanvas` absent.

## What has been checked

| Check | Result |
|---|---|
| Standalone engine/timing/Wasm integration | 61/61 cases |
| Native EGL graphics | 50/50 cases |
| Explicitly broken-EGL fault injection | 2/2 failure-handling cases |
| Python acquisition, input and pixel tools | 63/63 tests |
| Native scheduler | 12 checks, CTest 1/1 |
| Real browser capture-to-native round trip | **BLOCKED, not passed** |

The graphics tests cover actual pixel values, indexed drawing, typed-array offsets,
upload ownership, bounds checks, deleted and forged resources, cross-context
rejection, shader/link failures, stale uniform locations, resize clearing, memory
release, and hidden-state protection against guest prototype replacement. These
are custom regression cases, not WebGL conformance certification. A fresh offline
bundle clone reproduced the executable and framebuffer hashes and repeated the
standalone, graphics, failure-injection and tool tests.

## The outstanding game-input gate

Direct original-site acquisition failed in this environment. The new optional
capture helper connects to a fresh local browser's DevTools endpoint, but actual
navigation here returns `net::ERR_BLOCKED_BY_ADMINISTRATOR`, even for a localhost
fixture. The [integration report](reports/capture-integration.json) records zero
response bodies and zero compiled sources. That is a blocked test, not a success.

On a machine permitted to access the game, the development-only helper can be run
as a normal, non-root user:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-capture.txt
.venv/bin/python tools/capture_browser.py --url https://krunker.io/ \
  --seconds 30 --out input/krunker-capture
```

Use `.venv\Scripts\python.exe` on Windows. A current installed Chrome/Chromium
executable is required for this acquisition tool only. `--browser` selects its
path. Additional permitted asset origins require explicit `--allow-origin` flags.
This does **not** add a browser to the native runtime. It saves available script
and asset bodies plus compiled inline/eval source snapshots without rewriting
scripts, reusing a logged-in profile, hiding DevTools or bypassing checks.

Keep `input/` private and out of Git: bodies and URLs can contain secrets even
though cookies, authorization headers and POST data are omitted. Captured source
snapshots are not assumed to be separate runnable scripts or an execution order.
See [capture fidelity and limitations](docs/CAPTURE.md). Existing direct HTTPS and
HAR-with-response-contents routes remain in `tools/capture.py`.

## Runtime boundaries and dependencies

`bare` exposes engine facilities only. `core` adds documented console/timing
operations and `window/self` aliases, not a Window or document implementation.
`graphics` adds the explicit, limited surface documented in
[GRAPHICS.md](docs/GRAPHICS.md). Unsupported operations remain absent or return a
specific error; there are no success-returning texture/audio/network placeholders.

V8 13.6.233.17 is statically linked. Its source came from a V8 subtree vendored in
Node, but the Node runtime is not linked or launched. The optional graphics path
loads EGL and the system driver's dependencies dynamically. The binary audit
records both ELF dependencies and **runtime-loaded libraries**, not merely `ldd`.

The acquired SDK has **V8 sandbox and ICU/Intl disabled**. This is an experimental
bring-up dependency, not a hardened shipping configuration. A context, buffer
checks and watchdog are not an OS sandbox or a total memory limit; a stalled
native driver call cannot be interrupted by the JavaScript watchdog. Independent
SDK rebuilding, security/isolation work and a full redistribution-notice audit
remain open.

See [validation](reports/VALIDATION.md), [build instructions](docs/BUILD.md),
[runtime contract](docs/CONTRACT.md), [next gates](docs/NEXT.md) and
[provenance](docs/PROVENANCE.md). No Wok material was inspected. This remains a
local Git repository; no remote repository or fork was created.
