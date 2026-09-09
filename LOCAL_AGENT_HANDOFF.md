# Local-agent handoff — Krunker Zero 0.4 Windows source port

## Your assignment

Make the Windows build and native fixtures pass on this machine, then advance
original-game integration one observed missing contract at a time. Work in this
repository and retain its Git history. Start by reading `AGENTS.md`,
`docs/WINDOWS.md` and `reports/VALIDATION.md`.

**Absolute exclusion: do not open, search, inspect, clone, read, copy, compare
against or import Wok, including its docs, history, generated files or prior notes.**
Do not ask another agent to inspect it. This is a new independent implementation.
Do not perform broad searches through the user's other projects to find it.

The shipping target must not depend on Chromium, Electron, Node, CEF, a WebView,
a DOM emulation library or a fallback browser. Standalone V8 and standalone ANGLE
are allowed. Build tools and the separate development capture tool are not part
of the shipping runtime. Do not turn either into its runtime foundation.

## Honest starting state

Linux standalone V8, timers, microtasks, bounded diagnostics, synchronous and
asynchronous Wasm, and a real offscreen EGL/GLES graphics subset have passed
independent regression fixtures. The Windows source port adds MSVC/x64 setup,
Windows DLL loading, UTF-8/UTF-16 paths, ANGLE/D3D11 or explicit WARP, a native
fixed-size Win32 fixture window, presentation and foreground input plumbing.

**The Windows compiler path, source dependency builds, executable linkage,
DLL load path, actual window, keyboard and mouse have NOT been executed in the
handoff environment.** New portable unit tests and passing Linux tests are not
Windows acceptance. There is no prebuilt Windows executable in this handoff.

**No current original Krunker game code has executed.** There are no playable game
sessions or performance results. No audio, guest HTTP/WebSockets, texture/image
loading, full relevant WebGL/GLSL surface, HUD/DOM adapter, login, menus or real
gameplay. The Win32 fixture is not evidence that the game works.

The existing Linux SDK disables sandbox and Intl. The Windows source recipe
requests sandbox enabled and Intl disabled; verify `--engine-info` and the exact
header/library flags after building. A V8 sandbox is not an OS isolation boundary
for native host/driver defects. The V8 pin is a bring-up pin, not a claim of a
current secure deployment version.

## Gate 1 — establish a genuine native Windows build

Use x64 Developer PowerShell or x64 Native Tools Command Prompt for VS 2022:

```powershell
py -3 tools/windows.py doctor
py -3 tools/windows.py deps --work C:\kz-deps
py -3 tools/windows.py build
.\build\windows\zero.exe --engine-info
```

The source recipes are pinned in `config/windows-deps.lock.json`, and implemented
in `tools/windows_deps.py`. They use official upstream sources. Preserve build
logs and exact failing commands. Resolve compiler/Windows SDK/GN differences
explicitly; do not skip checks to get a green result. Do not use a Linux `.a`
archive, borrowed Node isolate, copied browser DLL or mismatched V8 header as a
Windows workaround. Do not synthesize a successful dependency receipt.

An existing unrelated work directory is refused, not cleaned. Use a short ASCII
source dependency path. For another trusted SDK, use the explicit CMake path in
`docs/WINDOWS.md`; its architecture, generated ABI macros and CRT must match.

First prove `zero.exe --engine-info` identifies a standalone Windows-x64 engine.
Inspect V8 sandbox, compression and Intl fields, and check PE/import/module reports.

## Gate 2 — execute tests before game-specific additions

```powershell
py -3 tools/windows.py test --angle-backend d3d11
py -3 tools/windows.py test --angle-backend warp --reports reports/windows-warp
py -3 tools/windows.py test --angle-backend d3d11 --interactive --reports reports/windows-interactive
py -3 tools/windows.py demo
```

Use an actual desktop for interactive tests. WARP-only passes must remain labeled
software rendering; an unavailable hardware driver does not count as a hardware
pass. The pipeline stops on failure. Retain partial output and a clear blocked
result rather than changing assertions to accept it.

`reports/windows*/` must contain the engine, core, graphics, platform and own-child
module-audit results. Check real framebuffer pixels and hashes, not only shader
compile return values. Confirm bare/core run without ANGLE DLLs; CWD/PATH must not
supply a missing app-local DLL. Test source/executable paths with Unicode/spaces.

The interactive automated test checks a real HWND/swap and close cancellation.
Physically verify keyboard events, relative `rawmousemove`, click-to-capture,
Escape and focus-loss release, minimize/restore and multiple DPI settings. This
input API reports virtual-key codes and native events, **not** DOM input events.
It does not include IME, gamepad, fullscreen or resize handling. Never capture
input outside the application's foreground window. Keep a reliable escape path.

Check `zeroWindow` stays absent without `--window`, and that `--window` rejects
virtual time. Native presentation cannot be validated using synthetic time.
Before performance work, remove or isolate diagnostics overhead and measure on
actual hardware; test counts are not compatibility percentages.

## Gate 3 — obtain original game input on the permitted local machine

The previous environment blocked even localhost browser navigation with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. Do not change/bypass browser policies,
authentication, anti-cheat, integrity enforcement or server restrictions.
A local machine permitted to access the game may use the separate capture tool:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-capture.txt
.\.venv\Scripts\python.exe tools/capture_browser.py --url https://krunker.io/ --seconds 30 --out input/krunker-capture
```

Read `docs/CAPTURE.md`. A normal installed browser is used for acquisition only.
Keep raw captures private/out of Git: bodies and URLs can include session data
although the helper omits cookies/auth headers/POST data. Do not publish captures
or upload them to CI. Do not substitute an old edited archive for current pristine
input. Confirm actual bodies, hashes, response status/content type and script
execution order. Network payloads and decoded/compiled snapshots have different
fidelity; do not blindly execute eval snapshots as independent global scripts.

## Gate 4 — the actual break/implement/rerun loop

Use `tools/probe.py --host build/windows/zero.exe` to execute a deliberately chosen,
ordered set of immutable script copies and retain SHA-256 provenance. Begin with
bare or the least profile actually required. Make the first genuine failure
reproducible; document what operation, input and output semantics the game needs.
Implement that contract, add regression tests, then run the unchanged input again.

Do not fabricate `document`, fill the entire DOM with proxies, return pretend
WebGL handles, fake audio/network completion, automatically claim extensions,
suppress feature detection, patch game logic or mark unfinished promises complete.
The current graphics methods are fixture-driven; only an original-game trace can
establish the subset the game needs. A successful single bootstrap is not a full
client. Recheck all paths used by menus, settings, in-game controls, assets and
reconnection before making playability claims.

## Where to work

- `native/main.cc`: native V8 lifetime, CLI, Windows wide entry point.
- `native/platform.*`: explicit DLL loading and UTF-8/filesystem boundaries.
- `native/win32_window.*`: HWND lifetime, foreground input and bounded event queue.
- `native/graphics.cc`: EGL/GLES ABI, contexts/resources, Windows backend selection,
  pbuffer/window surface and actual swap counters.
- `native/host.cc`: microtasks, timers, engine task pump, window message pump and
  watchdog; a close must stop remaining same-batch callbacks.
- `runtime/graphics.js`: minimal typed wrappers; fixture-only `zeroWindow` opt-in.
- `tools/windows*.py`: pinned dependencies, setup/build/test/demo/package driver.
- `tools/test_windows.py`, `tools/audit_windows.py`: native Windows acceptance.
- `.github/workflows/windows.yml`: supplied manual CI; never claimed run here.

Commit small changes with exact validation and limitations. The handoff is
complete when the next engineer can reproduce every claimed gate—not when a large
number of dummy APIs makes the initial exception disappear.
