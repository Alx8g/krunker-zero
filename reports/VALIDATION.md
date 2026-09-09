# Validation — 2026-09-09

## Passed

- **47/47 native V8 integration cases**, using the development-only Node/V8 adapter.
- **12/12 assertions in a separate native C++ scheduler executable** (CTest 1/1).
- **9/9 Python tool tests**, covering bootstrap markup inspection and input integrity.
- Standalone CLI source compiled to an object against the installed V8 headers.
- Native host and scheduler compiled into the development adapter with warnings enabled.
- Synthetic missing-DOM and clock fixtures executed through the probe tool, with
  exact-input SHA-256 and an explicit development-environment label in each report.

Command: `python3 tools/test.py`. Integration details: `test-results.json`.
Key source fingerprints: `source-hashes.json`.

## What the integration cases check

Bare globals genuinely absent; no Node process/require/Buffer API in the guest;
feature detection; uncaught missing-global classification; unchanged script order;
Promise checkpoint ordering; timeouts/intervals and arguments; self-cancellation and
same-batch cancellation; headless animation timestamps/deferred nested requests;
exceptions and rejected Promises; wall-clock termination of JS loops, Promise
loops and idle waits; callback/pending-work caps; configuration errors; JSON/Unicode
output; bounded logs. These are custom regression fixtures, not a full browser or
ECMAScript conformance suite.

The tests found and fixed V8's implicit debug-console exposure in a bare context,
and a pending termination request that could otherwise escape to the development
harness after an idle timeout. Neither bug is hidden by changing the assertions.

## Not validated / not implemented

The standalone executable has **not been linked or executed**. Matching standalone
V8 libraries are not installed, and outbound dependency downloads failed. The
production V8 platform/isolate startup and teardown paths remain unexecuted.

No Krunker bundle or game assets were loaded or executed. There is no current-game
API trace and no evidence of how many host contracts the game needs. No GPU window,
WebGL adapter, native input, audio, image decoder, network or server session exists.
There is no proof of compatibility with game integrity checks or server policies.
No anti-cheat/integrity/authentication bypass was attempted or implemented.

No FPS, binary-size, RSS, GPU, latency or playability comparison was performed.
The development adapter is not the proposed shipped runtime. Synthetic frame
callbacks do not render/present frames, and virtual time is not benchmark time.

## Environment and repository

Linux x86-64; GCC 14.2; CMake 3.31.6; Node 22.16.0; V8 12.4.254.21-node.26.
This is the observed environment, not a recommendation to deploy that engine.
All first-party work is in a fresh local `krunker-zero` Git repository. It has not
been published to GitHub. No existing user repository was inspected or modified.
