# Krunker Zero — 0.4 Windows source port

**Delete the browser. Keep the JavaScript engine. Add only evidenced host behavior.**

Start the Windows handoff with **[LOCAL_AGENT_HANDOFF.md](LOCAL_AGENT_HANDOFF.md)**
and **[docs/WINDOWS.md](docs/WINDOWS.md)**. `AGENTS.md` contains the exclusion rules.

## Status without the marketing

A standalone V8 C++ host and real EGL/GLES graphics subset run on Linux. The new
Windows source port targets **native x64**, with MSVC configuration, matching SDK
build recipes, app-local ANGLE/D3D11 loading, UTF-16/UTF-8 paths and an optional
Win32 fixture window with presentation and foreground input.

**Windows has not been compiled or executed in this handoff environment.** The
provided Windows commands and tests are for the local agent to execute. There is
no prebuilt Windows `.exe` or Windows SDK in the source kit. Passing Linux tests
and portable Python tests does not establish Windows compatibility.

**Krunker itself is not running on any platform in this project.** No current
original game bundle has executed. The triangle fixtures are independent test
code. Audio, guest networking, textures/image loading, game-specific host APIs,
complete relevant WebGL behavior, menus and actual gameplay remain unfinished.
There is no game FPS, latency, security or speedup claim.

## Windows local-agent workflow

In **x64 Developer PowerShell / x64 Native Tools Command Prompt for VS 2022**, with
Desktop C++, a compatible Windows SDK, Git, 64-bit Python 3.11+, CMake and Ninja:

```powershell
py -3 tools/windows.py doctor
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
[validation report](reports/VALIDATION.md) for exact executed tests. Old reports
are preserved under milestone-specific filenames; they are not current Windows
results. Platform-only C++ tests can be built without any V8 SDK by leaving
`ZERO_BUILD_V8_HOST=OFF` (the default).

## Original-game acquisition

The earlier environment blocked browser navigation, including localhost, with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. It collected no actual current game bodies.
Do not bypass that policy. The local agent can use the separate capture utility
on a machine permitted to access Krunker; see [CAPTURE.md](docs/CAPTURE.md).
This browser is a development acquisition tool only, never the native client's
runtime. Preserve body/source hashes, fidelity and execution order. Keep captures
private and out of Git. Compiled/eval snapshots are not automatically independent
scripts and should not be blindly replayed as globals.

## Boundaries

No Wok code, documentation or history was consulted. No remote repository or fork
was created. The local Git history continues the original independent repository.
V8 ABI flags and CRT must match their libraries. The Linux SDK disables V8 sandbox
and Intl; the Windows recipe requests sandbox on, Intl off and internal startup
data, but has not been executed here. Neither configuration is a hardened client
release. OS isolation, current engine patch selection and complete redistribution
notices remain work, not properties inferred from passing a fixture.
