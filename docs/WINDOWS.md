# Windows x64 — build and acceptance

Native Windows fixture acceptance is recorded at baseline `3d7cda7`; see
[CURRENT_STATUS.md](../CURRENT_STATUS.md). That baseline is not a binary release
or playable game. The current maintenance changes need a fresh Windows run using
[REVIEW_TESTING.md](REVIEW_TESTING.md), without overwriting baseline reports.

Target: native Windows 10/11 **x64** with an MSVC-compatible C++20 toolchain.
ARM64, 32-bit, MinGW, macOS and WSL-as-Windows are not supported by this recipe.
Windows 10 is an API target, not an operating-system security-support statement.

## 1. Start in the right shell

Install/use Visual Studio 2022 with **Desktop development with C++**, a compatible
Windows SDK, 64-bit Python 3.11+, Git, CMake 3.20+ and Ninja. Use **x64 Native Tools
Command Prompt for VS 2022**, or a Developer PowerShell configured for x64.
Ordinary PowerShell does not automatically provide `cl`, `dumpbin`, headers or
linker environment variables. The workflow never changes administrator/browser
policies or asks for a GitHub token.

From the repo root:

```powershell
py -3 tools/windows.py doctor
# For fresh dependency source builds, also check the pinned SDK prerequisites:
py -3 tools/windows.py doctor --source-build
```

If the Python launcher is unavailable, use `python` from the intended 64-bit
installation. Doctor must report `ready: true` before a host source build.
The pinned ANGLE build requires **Windows SDK 10.0.28000.0**, as discovered in
the Windows baseline. Doctor reports exact missing headers, x64 libraries and
tools. `deps` checks all pending source builds before beginning either download.
V8 and the remaining upstream toolchain checks still apply. Existing verified
SDK receipts and work-directory pins are unchanged by this maintenance patch.

## 2. Acquire/build matching standalone dependencies

```powershell
py -3 tools/windows_deps.py --plan
py -3 tools/windows.py deps --work C:\kz-deps
```

This performs real source builds of **V8** and **ANGLE**, using official upstream
URLs and fixed commits in `config/windows-deps.lock.json`. It does not build Chrome,
Electron, Node or an existing Krunker client. Chromium's build tools are build-time
dependencies only. The Windows kit does **not** contain compiled V8/ANGLE binaries;
it requires network access and substantial build disk space. The existing Linux
SDK cannot be used here.

Keep dependency checkout paths short, ASCII and without spaces. This restriction
is for upstream build launchers, not for running `zero.exe`. The runtime and local
acceptance tests support and check paths containing spaces and Unicode.
`C:\kz-deps` is a suggested path, not a required drive. A previously existing,
unmanaged directory is refused. Nothing is reset/cleaned destructively. A changed
lock or checkout requires a new work directory. Failed builds may be resumed at
the same pins. SDK destinations are staged atomically and never silently replaced.

Outputs:

```text
deps/windows-x64/v8/include/v8.h
                          /v8-gn.h
deps/windows-x64/v8/lib/v8_monolith.lib
deps/windows-x64/angle/bin/libEGL.dll
                            /libGLESv2.dll
```

Each component has a hash inventory, its actual gclient revision report, source
notices and build arguments. Reuse verifies the inventory; this is integrity
checking, not independent reproducible-build verification or a signed release.
The recipe requests **Release /MT**, pointer compression, internal V8 startup data
and **V8 sandbox enabled**. Intl remains disabled. The V8 generated ABI header must
come from the same build arguments. A separate header-generation directory avoids
injecting header-generation flags into the library build.

The source-build route completed in the Windows baseline. The new prerequisite
checks have portable unit coverage but still need Windows acceptance. If GN rejects
an argument or a toolchain is incompatible, retain the complete failing command
and log, fix the recipe explicitly and rerun. Do not suppress errors, invent a
receipt, mix Linux/Windows headers or define sandbox macros around a library that
was built without them. No latest/security-patch claim is made for the V8 pin.

## 3. Build the executable

```powershell
py -3 tools/windows.py build
.\build\windows\zero.exe --engine-info
```

The driver verifies the SDKs, configures Ninja/Release/x64 and copies the matching
ANGLE DLL pair beside `zero.exe`. Windows system libraries are linked explicitly.
The DLL loader uses absolute app-local paths and a restricted search policy; CWD
or PATH DLLs are not a fallback. The D3D shader compiler must be available through
Windows System32 or a verified matching app-local SDK copy; never download a
random similarly named DLL.

For a separately built/verified SDK, use CMake directly instead of fabricating
this recipe's receipt:

```powershell
cmake -S . -B build/windows-custom -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded -DZERO_BUILD_V8_HOST=ON -DZERO_BUILD_GRAPHICS=ON -DZERO_V8_ROOT=C:/sdk/v8 -DZERO_ANGLE_DIR=C:/sdk/angle/bin
cmake --build build/windows-custom --parallel 4
```

That SDK must supply `include/`, `lib/v8_monolith.lib` and matching `v8-gn.h`.
The CRT option must match the actual library; `/MT` versus `/MD` disagreement is a
real ABI problem, not a linker warning to silence. Debug libraries are not
interchangeable with this Release recipe.

A genuinely graphics-free build uses a **separate** directory:

```powershell
py -3 tools/windows.py build --core-only --build-dir build/windows-core
py -3 tools/test.py --host build/windows-core/zero.exe --report reports/windows-core-tests.json
```

## 4. Execute acceptance gates

```powershell
py -3 tools/windows.py test --angle-backend d3d11
```

This runs native platform/scheduler tests, standalone JS/Wasm tests, actual pixel
fixtures, a framebuffer PNG readback, Windows path/loading tests and PE/runtime
module audits. Full output is stored under `reports/windows/`. Nonzero status stops
the pipeline. Do not relabel failures as unsupported/skipped without retaining
that limitation in the report.

On a headless runner, select **WARP explicitly**:

```powershell
py -3 tools/windows.py test --angle-backend warp --reports reports/windows-warp
```

WARP results are software-renderer results, not hardware acceleration or game FPS.
The native backend never silently changes a failed hardware request to WARP.
`--angle-backend` is rejected outside Windows graphics. `zeroWindow` is absent
unless `--window` is passed; bare/core do not load ANGLE.

On a logged-in Windows desktop:

```powershell
py -3 tools/windows.py test --angle-backend d3d11 --interactive --reports reports/windows-interactive
py -3 tools/windows.py demo
```

The demo is an **independent animated triangle, not Krunker**. It uses a real Win32
window and EGL buffer swaps. Click inside it to request foreground pointer capture;
Escape or focus loss releases capture, and Escape also closes this demo. Native
counts distinguish scheduled callbacks, successful swaps and dropped input events.
Moving the mouse is required to observe actual `rawmousemove` events. No global
hook or background input sink is installed.

Physically verify keyboard/mouse events, Alt+Tab release, minimize/restore, close,
Escape release and behavior at 100/150/200% DPI. The fixture window is deliberately
fixed-size. DOM KeyboardEvent/MouseEvent, browser pointer-lock semantics, IME/text
input, full-screen, resizable swap chains, controller input and game controls remain
separate work. An EGL swap counter is not proof that a user saw the frame.

## 5. Optional private development package

After real acceptance, retain reports and run:

```powershell
py -3 tools/windows.py package --out dist/krunker-zero-windows-dev.zip
```

This packages the locally built executable, verified DLLs, notices, fixture and
file hashes. It refuses an existing destination. Packaging does not certify tests
or grant redistribution rights. Complete first-party licensing, third-party
notices, source/security review, OS isolation and update policies before release.
The handoff source archive itself contains no Windows executable or SDK binary.

`.github/workflows/windows.yml` is a **manual, unexecuted** CI recipe. Its default
job tests platform-only code; enable its source-build input to build V8/ANGLE and
run WARP fixtures. It does not prove desktop input or hardware-driver behavior.

## Primary references used for this implementation

- V8 build: https://v8.dev/docs/build
- V8 embedding/ABI: https://v8.dev/docs/embed
- V8 source pin: https://github.com/v8/v8/commit/b0a55a7dad7f536cce1f9aaddba89894c8533946
- V8 Windows system dependencies: https://github.com/v8/v8/blob/b0a55a7dad7f536cce1f9aaddba89894c8533946/BUILD.gn
- ANGLE standalone setup: https://github.com/google/angle/blob/041e83047db3e3b45f51cf98daba407583a1b2eb/doc/DevSetup.md
- ANGLE backend build flags: https://github.com/google/angle/blob/041e83047db3e3b45f51cf98daba407583a1b2eb/gni/angle.gni
- ANGLE EGL D3D device selection: https://chromium.googlesource.com/angle/angle/+/HEAD/extensions/EGL_ANGLE_platform_angle_d3d.txt
- Microsoft DLL flags: https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-loadlibraryexw
- Microsoft default DLL search: https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-setdefaultdlldirectories
- Microsoft Raw Input: https://learn.microsoft.com/en-us/windows/win32/inputdev/about-raw-input

The docs describe upstream contracts. They are not evidence that our Windows
source build or implementation has passed native Windows tests.
