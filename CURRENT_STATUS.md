# Current status — 9 September 2026 maintenance review

## Three separate states

**Windows baseline, upstream `3d7cda7`:** The local agent recorded real standalone
V8 and ANGLE source builds, 67/67 core tests, 52/52 graphics tests on both D3D11
and explicit WARP, 13/13 interactive platform checks, and two native test
executables. A native 640x480 fixture recorded 300 presented frames on Intel Iris
Xe through D3D11. V8 sandbox and pointer compression were enabled, Intl disabled.
These results are in `AGENT_HANDOFF.txt` and `reports/windows*/`; they were not
rerun on Windows in this review.

**This maintenance patch:** 100/100 standalone core cases, 52/52 native graphics
cases, two deliberate graphics-failure cases, two native test executables and
2,048 byte-level query differential vectors pass on Linux. See
`reports/review/VALIDATION.md` for tool tests and reconstruction details. This patch
is ready for local Windows regression, not approved as Windows-tested code yet.
The original dependency pins, CRT selection and SDK receipts are unchanged.

**Game integration:** The baseline handoff records 33 private response bodies and
123 compiled-source snapshots, not complete game coverage. Its initial timestamp
script and FRVR SDK ran; the channel script advanced past URLSearchParams and
stopped at missing `document`. A `location` reference is also required by the
constructed context. Their actual member operations have not been traced here.
No private input was available for this review, and no new bootstrap/gameplay
success is claimed. Never invent placeholder globals to erase the next error.

## Fixed in this patch

URLSearchParams no longer loses appends when argument conversion calls `delete`
or `set` on the same instance. Record/sequence inputs now handle callable objects,
null iterator methods, enumerable symbol keys and normalized record-key collisions.
Arguments are converted in order; receiver checks and iterator creation reject
invalid receivers immediately. `forEach`, `keys` and `values` no longer depend on
a guest-overridden `entries` method. Existing live iteration behavior is retained.
This is an existing API repair, not a new DOM/URL implementation or full Web IDL
conformance claim. Iterator prototype shape and arbitrary intrinsic tampering
remain outside the claimed surface.

The dependency driver checks the pinned ANGLE Windows SDK 10.0.28000.0 files before
any fresh multi-component source build. Doctor distinguishes host build readiness
from fresh dependency source readiness; verified installed SDK reuse is preserved.
The audit separates loaded modules from PE import declarations, checks the actual
host and app-local ANGLE paths, and requires the requested backend and an actual
context/device report. Empty snapshots are not credited as observations.

## Still not verified or implemented

Physical keyboard/raw mouse, cursor capture release, minimize/restore and multiple
DPI settings remain unverified; the baseline demo recorded zero raw mouse events.
Audio, guest networking, textures/images, measured DOM/GL contracts, complete
bootstrap, menus, authentication, matches and reconnect remain unfinished. No game
FPS, latency, minimum-footprint, secure-shipping or speedup claim exists.

Read `docs/REVIEW_TESTING.md` for the next Windows run. Preserve the original
agent's ignored capture/build/SDK files. Do not publish captures or rebuild SDKs
just because the runtime JavaScript changed.
