# Experimental native graphics contract

The `graphics` profile is a **fixture-driven bring-up subset**, not WebGL 1
certification and not an established list of Krunker's required calls. It is
excluded from the default build and from `bare`/`core` even in an enabled build.

## Execution path

```text
Unchanged independent JavaScript fixture
  -> embedded V8
  -> small JavaScript receiver/opaque-handle wrappers
  -> C++ validation and resource ownership
  -> public EGL / OpenGL ES driver entry points
  -> real offscreen framebuffer
  -> readPixels -> checked PNG encoder
```

There is no DOM, Chromium, Electron, Node, browser renderer, native window or
presentation callback. `presented_frames` is explicitly zero. Headless animation
callbacks remain timing callbacks, not a display's refresh or presentation clock.

The backend uses `dlopen("libEGL.so.1")`, the EGL surfaceless platform, a pbuffer
and an OpenGL ES context. GL entry points are obtained from `eglGetProcAddress`.
A small public ABI declaration slice replaces the need for development headers;
it does not replace the graphics driver. Only Linux x86-64 was tested.

The observed device is `llvmpipe (LLVM 19.1.7, 256 bits)` with
`OpenGL ES 3.2 Mesa 25.0.7-2`. Real software rasterization passes the pixel tests.
Hardware acceleration, latency, game FPS and other drivers are **not validated**.
The runtime library audit includes Mesa/LLVM and their dependencies; these cannot
be excluded from an honest deployment-footprint discussion.

## Implemented operations

`OffscreenCanvas` supports positive integer width/height from 1 through 2048 and
`getContext('webgl')` / `'experimental-webgl'`. Each canvas retains one context.
`webgl2`, `2d` and unsupported context kinds return null. This object is not a DOM
canvas; no document creation/lookup, event dispatch or transfer operation exists.

The exposed GL-shaped operations are:

- Clear/color/depth masks, viewport, selected enables/disables, depth function,
  finish/flush, error retrieval, a small parameter-query subset, and RGBA8 readback.
- Actual vertex/fragment shader creation, source, compilation, status/log queries
  and deletion; program creation, attach/link/status/log/use/deletion.
- Attribute/uniform lookup and `uniform4f`; buffer creation/binding/upload/subdata/
  deletion; FLOAT attribute layouts, enable/disable, drawArrays and drawElements
  with unsigned-byte or unsigned-short indices.

See `runtime/graphics.js` for the exact method and enum inventory. There are **no**
texture methods, image decoding, uniform matrices, uniform arrays, framebuffer
objects, instancing, vertex-array objects, WebGL extensions, context-loss events,
shader translation/validation layer, context-loss detection, Canvas2D, text or HUD layout.
`isContextLost` is absent rather than an unconditional false-returning placeholder.

Only an RGBA/depth pbuffer is created. Reported context attributes describe this
experimental path: alpha/depth true, antialias/stencil false. Requests for
alpha:false, premultipliedAlpha:false, or failIfMajorPerformanceCaveat:true are
rejected rather than pretending a supported alternate surface exists. General
WebIDL coercion and every browser context-attribute semantic are not implemented.
The version/renderer queries report the native GLES driver, not a spoofed browser.

## Resource and memory rules

Native GL names never appear as public JavaScript handles. Per-context native
maps own the real resources; JavaScript receiver/handle branding uses private
WeakMaps and cached intrinsics. Forged, deleted and cross-context handles are
rejected by the implemented entry points. Uniform locations are tied to a program
and its link generation. No successful no-op operations fabricate native state.

Typed-array inputs honor byteOffset/byteLength. Backing-store lifetime is held
while native code uses it; detached/shared buffers are rejected. Buffer upload
copies data and maintains a CPU shadow for bounds checking; subsequent mutation
of a JavaScript input is not treated as a GPU update. Numeric allocations are
zero initialized. Actual deletion releases the CPU shadow allocation, not just
its logical size; regression evidence checks native retained capacity equals zero.

Draws validate enabled attribute byte ranges; indexed draws also validate the
index byte range and scan indices before issuing the driver call. Readback checks
the RGBA/UNSIGNED_BYTE/Uint8Array combination and destination size before writing.
Only the requested view changes; clipped off-buffer regions become zero. New and
resized drawing buffers are cleared even when prior write masks/scissor interfere.

Caps: 8 contexts per run; 4096 lifetime resource records per context; 64 MiB of
logical shadow-buffer bytes per context and per transfer; 1 MiB UTF-16 code units
per graphics string. Resource records are deliberately not recycled during a run.
These caps are **not** a total process/driver memory limit. Driver allocations,
V8 memory, shader compilation and temporary upload copies have additional costs.
No secure-GPU-sandbox claim or untrusted-shader certification is made.

## Validation and error boundaries

`tools/test_graphics.py` uses actual EGL for every one of its 50 cases.
`tools/test_graphics_failures.py` separately builds deliberately broken test-only
EGL libraries to check repeatable error handling for missing symbols and failed
initialization. Those fake libraries never serve as a rendering fallback.

`tools/render_probe.py` runs the independent triangle fixture, checks native
operation counts and complete readback rows, converts bottom-up RGBA to top-down
RGB, then writes the observed pixels as PNG. `reports/render-probe.json` preserves
raw row logs and hashes of the fixture, executable, RGB pixels and PNG.

Errors are explicit, but the implemented error/coercion behavior is only the
specified subset. Native driver calls are synchronous; the JS watchdog cannot
preempt a hung driver call or bound driver compilation resources. V8/OS/graphics
isolation, full GL error semantics and behavior on additional drivers remain open.

## Public interface references

- WebGL 1 interface and validation: https://registry.khronos.org/webgl/specs/latest/1.0/
- EGL: https://registry.khronos.org/EGL/
- OpenGL ES: https://registry.khronos.org/OpenGL/index_es.php
- Mesa EGL implementation: https://docs.mesa3d.org/egl.html

These are interface references, not borrowed client implementation code.
