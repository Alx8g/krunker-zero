# Next acceptance gates

## 1. Standalone executable

Provide a maintained, pinned V8 build with matching headers/ABI/data files. Link
`zero`, run the synthetic probes without a Node process, verify initialization and
teardown under an OS memory cap, and run the same contract suite against that CLI.
Keep actual standalone test results separate from the development-adapter results.
This gate is not complete merely because `native/main.cc` compiles.

## 2. First original-game dependency

Obtain an authorized current original game bootstrap and its required original
script inputs. Keep them in ignored local storage. Record retrieval origin/date,
bytes and SHA-256; establish execution order rather than guessing `game.js` names.
Run bare, record the first reachable host dependency, and reduce it to an independent
fixture. There is **no current Krunker dependency trace** in this repository yet.

## 3. Incremental host contracts

Implement only the operation that is actually reached, including relevant return
values, error cases and lifecycle/ordering. Rerun the unchanged bundle. Add actual
scenario evidence to `reports/capabilities.json`. A fixture-only capability must
not be promoted to game-required or game-verified without that evidence.

## 4. Native frame and interaction

Once actual calls justify graphics/input dependencies, bind a native window and
validated graphics subset. Verify pixels, real mouse/keyboard events, and a visible
frame from the unchanged game. Integrate audio/network only as demonstrated.
Do not add a browser fallback to make this milestone appear complete.

## 5. Playability and performance

Exercise the relevant menus, local gameplay, settings, resizing, focus changes,
asset loading, supported server connection and reconnect flows with permission.
Only then compare correct full-workload performance against a browser baseline.
Neither passing unit tests nor reaching a menu gives a meaningful percentage of
completion or guarantees a speedup.
