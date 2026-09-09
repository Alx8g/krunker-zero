# Validation — 0.4 Windows source-port handoff, 9 September 2026

## What this milestone does and does not establish

Windows x64 source support has been implemented, with build/dependency recipes,
MSVC configuration, UTF-8/UTF-16 paths, app-local DLL loading, ANGLE backend
selection, a Win32 fixture window, actual-swap plumbing and foreground input.
**Windows compilation, linkage, SDK source builds, DLL execution, presentation,
physical input and Windows CI have NOT been executed here.** No Windows binary
or SDK binary is included in the source handoff.

The environment is Linux. The Windows acceptance runner was invoked here and
correctly returned nonzero with `status: not_run`, zero passed and zero total.
That result is preserved, not relabeled a Windows pass.

## Executed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Linux standalone V8/core/Wasm | **61/61 passed** | `windows-port-linux-core.json`, `.log` |
| Linux real native EGL pixel/resource fixtures | **52/52 passed** | `windows-port-linux-graphics.json`, `.log` |
| Linux deliberate broken-EGL fault tests | **2/2 passed** | `windows-port-linux-failures.json`, `.log` |
| Python tools, including portable Windows-helper tests | **94/94 passed** | `windows-port-python.log` |
| Linux native scheduler | **12 checks passed** | CTest `native_scheduler` |
| Linux native platform loader/Unicode paths | **12 checks passed** | CTest `native_platform` |
| Native CTest suite | **2/2 executables passed** | `windows-port-linux-native.log` |
| Real Linux triangle readback | **128x128 pixels encoded and hashed** | `windows-port-linux-render.json`, `windows-port-linux-triangle.png` |
| Linux core module audit | **5 observed system shared libraries; no EGL, browser or Node images** | `windows-port-linux-core-audit.json` |
| Linux graphics module audit | **41 observed runtime libraries; no browser or Node images** | `windows-port-linux-graphics-audit.json` |
| Fresh Git clone and offline Linux rebuild | **passed; repeated 61 core, 52 graphics, 2 fault tests, 94 Python tests and CTest 2/2** | `windows-port-rebuild.json`, `windows-port-rebuilt-*` |
| Windows acceptance on this Linux machine | **NOT RUN, nonzero exit** | `windows-port-windows-not-run.json` |
| Windows prerequisite doctor on this machine | **not ready** | `windows-port-doctor-linux.json` |

These tests are not Krunker compatibility percentages, full WebGL certification,
Windows runtime evidence, security assurance or performance measurements. The
observed Linux driver remains llvmpipe, a native software renderer. The Linux
pbuffer fixture presents no window frames. No real-game inputs were executed.

## Clean reconstruction

The final fresh clone tested source commit
`3bf3158d60d1ae284c23a115ca158bc8a2bb4d30`.
It used the previously verified Linux-only V8 SDK from a local archive. Source
and all fixture/tool inputs needed by the test suite came from the Git clone.

- Original and reconstructed Linux executable SHA-256:
  `6a261e97e9b06be14bee8f4dbadfea281668959697c5440ce9e4f0c94eb8b463`.
- Original and reconstructed PNG SHA-256:
  `b3272b9573fdb9674d7c2e58c711138eee4a9e1832dbc0a972fcb7a90e6b26da`.

Both matched. This is same-compiler/same-driver reconstruction, not an independent
V8 build or cross-platform reproducibility proof. A first clone caught an omitted
untracked Windows demo fixture. The fixture was added to Git; the second fresh
clone passed. The initial failing log is retained as
`windows-port-initial-rebuild-failure.log`.

## New contracts and review fixes

Windows host entry is wide-character `wmain`; script input and diagnostic names
cross an explicit UTF-16/UTF-8 boundary. ANGLE DLLs load from the executable's
directory through restricted Win32 loader flags. Requests explicitly select
D3D11 hardware or WARP and fail rather than silently substituting a backend.
Generated V8 ABI headers and the Windows release /MT library must match.

The source-only Win32 fixture API is absent without `--window`, is rejected in
virtual time and is not a DOM/pointer-lock implementation. It owns a fixed-size
window, pumps bounded foreground input, exposes keyboard/native relative mouse
records and counts only successful EGL swaps as presented frames. Cursor capture
is foreground-only and released on Escape/focus loss, close, minimize/move and
system-menu/modal changes. EGL surfaces are released before the HWND. Local
physical input, DPI and driver validation remain mandatory.

Review also corrected a Unicode resource-macro mismatch in Windows compiler
definitions, prevented event-object creation from invoking guest prototype
setters, stopped same-batch callbacks after a requested window close, and removed
an unsupported uniform call from the demo. The demo's shader/uniform contract is
separately pixel-tested on a Linux pbuffer; that does not validate the Win32 demo.
EGL config selection now searches actual returned formats rather than assuming
the first minimum-size match is the supported exact RGBA8 format.

The Windows Python helpers have pure tests for official pins, GN argument
serialization, SDK integrity/ABI/CRT mismatches, DLL-module audit decisions,
paths and subprocess command construction. These are tooling unit tests only;
no mocked SDK was used to claim native linkage or graphics success.

## Windows local acceptance plan

Read `LOCAL_AGENT_HANDOFF.md` and `docs/WINDOWS.md`. Run the doctor, pinned source
SDK build, native host build, core/graphics/platform tests and own-child module
audits on Windows x64. Run WARP separately with explicit software labeling.
Desktop HWND/swap/close tests require `--interactive`; keyboard/raw mouse/capture
release and DPI require real physical interaction with the demo.

The SDK source recipe, its fixed pins, /MT validation, batch launchers and generated
header staging have not been end-to-end tested on Windows. Retain and fix actual
build failures rather than treating this unexecuted recipe as a validated SDK.
The included manual GitHub workflow was not dispatched.

## Remaining game and release work

No current original Krunker script/asset execution, gameplay or server session.
Audio, guest networking, images/textures, the measured game-required browser/GL
contracts and real menus/settings remain missing. The prior acquisition blocker
was not bypassed. A permitted local capture is still needed for game-specific
work; raw captures stay private and out of Git.

The Linux SDK is V8 13.6.233.17 with sandbox and Intl disabled. The Windows source
recipe requests sandbox enabled and Intl disabled at a fixed upstream commit,
but that configuration has not run here. Neither a V8 context nor a native
watchdog establishes OS isolation or production-safe guest execution. Driver calls
may stall outside the JS watchdog. Engine patch selection, complete license/notice
review, hardening, hardware tests and performance measurement remain open.

No Wok source/docs/history were inspected. Work remains in the independent local
Git history; no remote repository, fork, release, deployment or CI run was created.
`V0.3-VALIDATION.md` and earlier milestone reports preserve previous claims.
