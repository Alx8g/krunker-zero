# Krunker Zero — browserless native runtime

**Delete the browser. Keep the JavaScript engine. Add only evidenced host behavior.**

Start with **[CURRENT_STATUS.md](CURRENT_STATUS.md)** and
**[docs/REVIEW_TESTING.md](docs/REVIEW_TESTING.md)**. `AGENTS.md` contains the project
boundaries. `LOCAL_AGENT_HANDOFF.md` is the historical v0.4 starting assignment;
`AGENT_HANDOFF.txt` records the subsequent native Windows baseline.

## Status without the marketing

The baseline branch `fix/windows-native-acceptance` at `3d7cda7` contains recorded
native Windows V8/ANGLE builds, 67 core cases, 52 graphics cases per backend,
13 interactive platform checks, and a 300-frame Intel Iris Xe / D3D11 window demo.
These are fixture results, not playable Krunker or game performance evidence.

The maintenance patch corrects URLSearchParams semantics, Windows SDK preflight,
module-audit evidence gates, and stale status records. Its 100 standalone core
cases, 52 graphics cases and 2,048 query-string differential vectors pass on
Linux. **This patch still requires the local Windows regression run.**

**Krunker is not playable.** The baseline handoff records execution of the initial
timestamp script and FRVR SDK; the next channel script stops at missing `document`
after query support was added. `location` is also absent. Raw captures and Windows
executables/SDKs are deliberately outside Git. No new game capture was available
in this maintenance review. Audio, networking, textures/assets, remaining
measured host contracts, menus and matches remain unfinished.

## Windows local-agent workflow

In **x64 Developer PowerShell / x64 Native Tools Command Prompt for VS 2022**, with
Desktop C++, Git, 64-bit Python 3.11+, CMake and Ninja. The pinned ANGLE source
requires Windows SDK 10.0.28000.0 (including headers, x64 libraries and tools):

```powershell
py -3 tools/windows.py doctor --source-build
py -3 tools/windows.py deps --work C:\kz-deps
py -3 tools/windows.py build
py -3 tools/windows.py test --angle-backend d3d11
py -3 tools/windows.py demo
```

The dependency step builds pinned **standalone V8 and ANGLE**, not a browser.
It needs network/build space; the existing Linux SDK is not a Windows substitute.
Native output is `build/windows/zero.exe`, with matching ANGLE DLLs beside it.
For headless graphics testing choose `--angle-backend warp` explicitly and retain
software-renderer labeling. Use `test --interactive` on a real Windows desktop
for HWND/swap/close checks; manually verify physical input and capture release.

The demo uses the opt-in `zeroWindow` fixture API. It is not a game window or a
complete implementation of browser input. Bare/core profiles do not load ANGLE;
`zeroWindow` is absent without `--window`. No browser/Node fallback exists.

See [WINDOWS.md](docs/WINDOWS.md) for dependency integrity, alternate SDKs, a minimal
build, known limitations, output packaging and failure handling. The manual CI
recipe is supplied but has not been run.

## Linux regression workflow

The separately supplied **Linux-only** locked SDK remains usable:

```sh
python3 tools/bootstrap_v8.py --archive ../v8-13.6.233.17-linux-x64.zip --build
cmake -S . -B build/standalone -DZERO_BUILD_GRAPHICS=ON
cmake --build build/standalone -j2
ctest --test-dir build/standalone --output-on-failure
python3 tools/test.py --host build/standalone/zero
python3 tools/test_graphics.py --host build/standalone/zero
python3 tools/test_graphics_failures.py --host build/standalone/zero
python3 tools/render_probe.py --host build/standalone/zero
```

The actual Linux renderer observed here is llvmpipe: real native software
rasterization, not hardware acceleration. The framebuffer is an actual GL readback,
not a generated illustration or game screenshot. Consult the current
[maintenance validation report](reports/review/VALIDATION.md) for exact executed tests. Old reports
are preserved under milestone-specific filenames; they are not current Windows
results. Platform-only C++ tests can be built without any V8 SDK by leaving
`ZERO_BUILD_V8_HOST=OFF` (the default).

## Original-game acquisition

The earlier environment blocked browser navigation, including localhost, with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. It collected no bodies in that earlier environment. The Windows baseline later
recorded a successful private capture of 33 response bodies and 123 compiled
snapshots; those private inputs are not in Git. Do not bypass policies. Use the separate capture utility
on a machine permitted to access Krunker; see [CAPTURE.md](docs/CAPTURE.md).
This browser is a development acquisition tool only, never the native client's
runtime. Preserve body/source hashes, fidelity and execution order. Keep captures
private and out of Git. Compiled/eval snapshots are not automatically independent
scripts and should not be blindly replayed as globals.

## Boundaries

The implementation remains independent; the project exclusions in AGENTS.md
remain in force. A public repository now exists at Alx8g/krunker-zero.
V8 ABI flags and CRT must match their libraries. The Linux SDK disables V8 sandbox
and Intl. The Windows baseline reports sandbox on, Intl off and internal startup
data; this review did not rerun Windows. Neither configuration is a hardened client
release. OS isolation, current engine patch selection and complete redistribution
notices remain work, not properties inferred from passing a fixture.
