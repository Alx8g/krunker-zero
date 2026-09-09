# Maintenance validation — 9 September 2026

## Scope and source provenance

Target: fixes relative to `Alx8g/krunker-zero`, branch
`fix/windows-native-acceptance`, upstream `3d7cda7bac71896e5e1d1457e254d2a0d9f132cd`.

Direct container GitHub downloads failed. The original v0.4 Git bundle was restored,
and all six source/test files changed by the Windows agent were read through the
GitHub connection and reconstructed with matching Git blob hashes. The changed
capability ledger was also hash-matched. `source-import.json` records the six
source hashes. This is a source reconstruction, not a complete clone of the new
Windows report tree and not a recreation of the upstream commit history. The
exported patch is relative to those verified current sources, not old main.

Tests below ran in this Linux environment against the standalone V8 library from
the previously SHA-256-verified offline SDK. No browser or Node fallback was used
by the native executable. That Linux SDK disables sandbox and Intl. The upstream
Windows reports have a different build configuration and were not rerun here.

## Executed results

| Check | Result | Report |
|---|---|---|
| Original branch-source core suite | 67/67 | baseline-core.json |
| Updated standalone core suite | 100/100 | core-tests.json |
| Core suite on graphics-enabled executable | 100/100 | graphics-build-core-tests.json |
| Native Linux graphics/resource fixtures | 52/52 | graphics-tests.json |
| Deliberate missing-symbol/failed-EGL tests | 2/2 | graphics-failure-tests.json |
| Native scheduler/platform executables | 2/2 | native-tests.log |
| Python tool unit tests | 133/133 | python-tests.log |
| Independent query differential vectors, seed 3909 | 2,048/2,048 | query-differential.json |
| Additional query stress vectors, seed 741 | 20,000/20,000 | query-stress.json |
| Windows audit invocation on this Linux machine | not_run, nonzero | windows-audit-not-run.json |

The differential runs overlap some byte-prefix vectors; their sizes are not a
claim of 22,048 distinct inputs. The oracle uses a separate Python byte-level
form parser, Python UTF-8 decoding and UTF-16 sort keys. Hand-written unit tests
check its important boundary expectations. It is not official WPT certification.

`source-hashes.json` records code/test inputs. The clean patch replay result is in
`replay-validation.json`. The SDK itself was not rebuilt from source in this review.

## Bugs reproduced before repair

`initial-bug-reproduction.json` contains eight demonstrated behavioral mismatches
in the old query implementation: reentrant append data loss, overridden entries
breaking forEach, null iterator handling, callable record handling, enumerable
symbol keys, normalized record collisions, late receiver validation and deferred
iterator receiver validation. Additional guarded cases exercise sequence conversion
ordering, live mutations, copied outputs and malformed UTF-8.

`audit-gate-reproduction.json` shows three synthetic decision inputs the old audit
accepted and the new audit rejects: PE-import-only ANGLE evidence, DLLs from the
wrong directory, and the wrong requested backend. These are decision unit tests,
not Windows observations. No native audit success is claimed in this environment.

## A reference failure was investigated, not hidden

The first randomized run used the installed Node v22.16.0 URLSearchParams as its
reference. It disagreed on literal Unicode adjacent to invalid percent bytes
(case 270). Its failing record is retained as
`query-differential-initial-failure.json`. The native parser preserved the UTF-8
emoji and BOM in `x=%b0🎮?%\uFEFF`, whereas that reference output corrupted them.
The WHATWG algorithm UTF-8-encodes the input before percent-decoding and forgiving
UTF-8 decode. The native behavior follows that sequence.

No native change was made to imitate the reference's discrepant result. The
reference runner was replaced by the separate Python byte-level implementation,
which checks the same literal-Unicode/malformed vectors without removing them.
That mixed case was also added as a permanent explicit native regression.

## Remaining acceptance

The new runtime JavaScript, SDK preflight and module-audit changes have NOT run on
Windows. `docs/REVIEW_TESTING.md` supplies native D3D11/WARP, interactive, differential
and physical-input instructions in separate report directories. SDK source pins,
CRT and receipt format were deliberately not changed; existing validated SDKs do
not need to be rebuilt merely to test this patch.

No current private bootstrap input was available here. `document` and `location`
are still absent; no new game execution or gameplay success is claimed. No FPS,
latency, size improvement, security certification or full Web IDL/WebGL conformity
is inferred from these test counts. URLSearchParams iterator prototype shape and
arbitrary intrinsic-tampering compatibility are not covered by the claimed subset.

The public repo was readable, but branch creation was rejected twice with HTTP 403,
`Resource not accessible by integration`. No remote branch, commit, PR, merge, CI
run or release was created by this review. A patch and agent handoff are provided
instead; the existing remote branches are unchanged by these attempts.

## Primary specifications consulted

- https://url.spec.whatwg.org/#urlsearchparams
- https://url.spec.whatwg.org/#application/x-www-form-urlencoded
- https://webidl.spec.whatwg.org/#es-record
- https://webidl.spec.whatwg.org/#es-sequence
- https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-module32firstw
- https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-module32nextw
- https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/nf-tlhelp32-createtoolhelp32snapshot
