# Project rules

This is a new, independent implementation. Work only in this repository.

Do not open, search, inspect, clone, read, copy, compare against, or import Wok,
including its source, docs, history, generated files, or prior implementation
notes. The user's exclusion applies even when it would make a task easier.
Do not use personal-context or library searches to retrieve that implementation.
Use original authorized game inputs, public platform specifications, engine
interfaces, and new regression fixtures instead.

No Chromium, Electron, CEF, WebView, DOM emulation library, or browser fallback in
the shipping target. Standalone V8 is allowed; it is the JS engine, not a browser.
Node is allowed only in explicitly marked development tests. Never turn that test
adapter into the shipping client or call its process metrics native-host metrics.

Default to absent capabilities. Add APIs only against an observed operation or a
clearly labeled optional test fixture. Record evidence in the capability ledger.
Preserve feature-detection behavior. Never advance by returning fake success,
fake graphics handles, stub audio completion, or unconditional WebGL success.

Keep original game bytes unchanged and out of Git. Do not bypass authentication,
anti-cheat, integrity checks, or service restrictions. A blocker there is reported,
not worked around. Do not expose arbitrary host filesystem or process access.

Always distinguish compile-only checks, development-adapter execution, standalone
execution, actual game execution, and measured performance. Test counts are not
compatibility percentages. Future graphics must preserve WebGL's relevant
validation and object/typed-array lifetime rules.

## Windows handoff rules

Windows x64 is the primary local acceptance target. Read `LOCAL_AGENT_HANDOFF.md`
and `docs/WINDOWS.md` first. Source portability work is not a Windows execution
pass; use `tools/windows.py test` on native Windows, and retain its JSON/logs.
Keep MSVC CRT, generated V8 ABI header and static library matched. Keep ANGLE DLLs
app-local and matched; no CWD/PATH search or silent WARP fallback. `zeroWindow` is
an optional fixture API, not a claim that DOM/pointer-lock behavior exists.
Never package raw captures. Do not trigger expensive CI source builds, publish a
release or modify another repository merely because the workflow file exists.
