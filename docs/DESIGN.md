# Direction: specialize the host, not the game

## The intended boundary

```text
Original, authorized game JavaScript and assets (local, versioned by hash)
                           |
                     standalone V8
                           |
             only demonstrated host contracts
                           |
            native graphics / input / audio / network
                           |
                      OS and drivers
```

Currently only the engine-facing headless host and timing contracts exist. The
native backend row is a design target, not implemented software.

V8 is chosen to retain a JIT-capable engine while removing the browser shell. V8
can be embedded independently of Chromium. A small interpreter such as QuickJS
would be useful for some discovery tasks, but choosing it solely for size could
trade away execution performance. There is no Krunker benchmark supporting an
engine comparison yet. No QuickJS source was obtained or incorporated.

Do not write a new JavaScript engine. Do not mistake fewer source lines, fewer
processes or a smaller download for lower input latency. Measure the actual game
once it works. Retain boundaries that enforce memory safety and API semantics.

## Why a bare run is valuable

Loading the original bundle into a fresh engine reveals the host contract rather
than starting with a large emulation library. Preserve native failure and feature
checks: `typeof missing` stays `undefined`; `'missing' in globalThis` stays false.
A proxy returning an object for everything takes different branches and fabricates
progress. The first probe deliberately reports only uncaught failures.

The current `core` profile is optional fixture-driven scaffolding. It is not a
measured minimum for Krunker. Once real input traces exist, split or remove optional
surfaces when that improves the measured deployed result.

## Graphics is more than renaming WebGL calls

A future graphics adapter must establish which WebGL version, extensions and
operations the identified bundle uses. A matching WebGL method includes relevant
validation, object ownership, typed-array bounds and offsets, shader behavior,
texture upload semantics and object lifetime. Forwarding unvalidated pointers to
native GL is not a correct minimal implementation.

Possible backends include a thin GLES path or a standalone translation library
such as ANGLE. No backend is selected or vendored here; select against actual
platform coverage and shader/extension evidence. Preserve a small adapter boundary
so the backend can change without rewriting the game. The first graphical desktop
target should be selected explicitly; this foundation was only tested on Linux.

A useful graphics acceptance gate is an independently specified draw with pixel
verification and negative validation cases, followed by an actual frame from the
unchanged game. A triangle alone is not proof the game runs.

## UI is the scope multiplier

The current Krunker public page exposes menus, overlays and HUD elements, so it
must not be assumed to be a single isolated canvas. A saved, identified bootstrap
must establish the actual dependencies. If the executed path reads geometry,
computed style, fonts or canvas text, returning fake dimensions is incorrect.
Implement a narrowly evidenced behavior or record that the unchanged-bundle goal
now requires more substantial UI support. Replacing the UI or patching out features
would be a separate, explicitly approved scope; this repo does neither.

## Async behavior is part of each API

Input must map to native event delivery and focus/pointer-lock behavior. Audio
must have real playback/clock semantics. WebSockets require binary payloads,
ordering, close/error behavior, buffering and certificate validation, not just a
successful TCP connection. Asset fetch needs decoding and task/microtask timing.
These are requirements to investigate when reached, not a prewritten API checklist
to implement before seeing the game use them.

## Future performance gate

Use identical game version, map, assets, settings, viewport/render resolution,
frame cap, vsync and warmed/cold conditions. Report render correctness first, then
frame-time distribution (including tails), actual input-to-present latency where
measurable, CPU/GPU utilization, whole-process memory and startup time. Record
hardware/driver/backend and separate simulation from real GPU presentation.
Never compare a headless skipped-render run to a functioning browser client.

## Sources consulted (2026-09-09)

- V8 embedding interface: `https://v8.dev/docs/embed`
- V8 engine overview: `https://v8.dev/`
- WebGL specification: `https://registry.khronos.org/webgl/specs/latest/1.0/`
- HTML timers: `https://html.spec.whatwg.org/multipage/timers-and-user-prompts.html#timers`
- Animation callbacks: `https://html.spec.whatwg.org/multipage/imagebitmap-and-animations.html#animation-frames`
- SDL native-context interface (not incorporated): `https://wiki.libsdl.org/SDL2/SDL_GL_CreateContext`
- QuickJS overview (considered, not incorporated): `https://bellard.org/quickjs/`
- Original public game landing page, not an extracted game bundle: `https://krunker.io/`

Design choices above are project proposals unless supported by actual test reports.
These references are platform specifications/interfaces, not another client's code.
