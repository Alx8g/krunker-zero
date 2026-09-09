# Next acceptance gates

## 1. Standalone bring-up — passed, production hardening still open

The pinned standalone SDK is acquired, linked, executed and exercised by the native
contract suite. Header ABI selection, startup, shutdown, missing APIs, Promise
settlement and asynchronous WebAssembly are validated. Fresh offline bootstrap
and bundle-clone rebuild results are recorded in reports/VALIDATION.md.

The acquired SDK omits V8 sandbox and Intl. A production engine configuration,
OS-level isolation, source-build verification, complete redistribution notices,
memory-limit behavior and other operating systems remain unvalidated. Do not
promote this bring-up engine to a secure shipping client.

## 2. First original-game dependency

Obtain an authorized current original game bootstrap and its required original
script inputs. Keep them in ignored local storage. Record retrieval origin/date,
bytes and SHA-256; establish execution order rather than guessing `game.js` names.
Run bare, record the first reachable host dependency, and reduce it to an independent
fixture. There is **no current Krunker dependency trace** in this repository yet.

The page-only DevTools acquisition helper is implemented and unit-tested, but its
real-browser round trip was explicitly blocked by administrator navigation policy
here, even on localhost. Direct game-body acquisition also failed. The metadata
reader's parsed homepage and an outdated, wrapper-modified public game archive
were not substituted for unchanged current input. An actual current permitted
capture is the outstanding external input, not another speculative host shim.

## 3. Incremental host contracts

Implement only the operation that is actually reached, including relevant return
values, error cases and lifecycle/ordering. Rerun the unchanged bundle. Add actual
scenario evidence to `reports/capabilities.json`. A fixture-only capability must
not be promoted to game-required or game-verified without that evidence.

## 4. Native frame and interaction — offscreen fixture rendering passed only

The optional EGL backend now compiles shaders, draws actual triangles, and passes
50 graphics cases plus two separate failure-injection checks. This is real
independent-fixture rendering through Mesa llvmpipe, not a Krunker frame or a
hardware performance result. A missing-symbol/configuration path fails explicitly.

Native window creation/presentation, real mouse/keyboard events, texture/image
loading, complete relevant GL behavior, UI, audio and game networking remain
unimplemented. Establish their required contracts from the unchanged current
bundle, then verify visible gameplay. A browser fallback cannot satisfy this gate.

## 5. Playability and performance

Exercise the relevant menus, local gameplay, settings, resizing, focus changes,
asset loading, supported server connection and reconnect flows with permission.
Only then compare correct full-workload performance against a browser baseline.
Neither passing unit tests nor reaching a menu gives a meaningful percentage of
completion or guarantees a speedup.
