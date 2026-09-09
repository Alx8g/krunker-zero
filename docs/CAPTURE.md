# Capturing actual game inputs without changing the native target

`tools/capture_browser.py` is an **optional development acquisition helper**, not a
client, browser fallback or native runtime dependency. It uses an installed local
browser's public DevTools protocol to save permitted GET response bodies and
compiled JavaScript source snapshots in a new private directory under `input/`.

## Local invocation

Run as an ordinary non-root user on a machine where navigation is permitted:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-capture.txt
.venv/bin/python tools/capture_browser.py --url https://krunker.io/ \
  --seconds 30 --out input/krunker-capture
```

Windows virtual-environment Python is `.venv\Scripts\python.exe`. Supply
`--browser /path/to/chrome` when automatic discovery does not find it. `--headless`
is optional; a normal visible fresh browser is the default. The window and its
fresh profile are closed after the bounded capture. No user's existing profile,
login session or open tabs are inspected. Windows/macOS operation is unvalidated.

Only the page origin is initially allowed for saving. Additional known asset
origins can be explicitly enabled with `--allow-origin https://asset-origin`.
This restricts what is **recorded**; it is not a browser network firewall. The
browser still performs normal page navigation and requests.

Cookies, request/response headers, authorization headers and POST data are not
saved. URLs, compiled sources and response bodies may nevertheless contain
session-specific or sensitive data. Do not commit or publish captures; `input/`
is ignored by Git. Preserve captures privately for analysis. No font files are
captured by this tool or distributed in the handoff.

## What is retained

The collector stores selected HTML, JavaScript, Wasm, raster image and audio
responses from allowed origins and GET requests. Each stored body has a SHA-256,
byte length and content-addressed relative path. Identical bodies are deduplicated,
but metadata records remain separate. Non-200 responses, unavailable bodies,
HTML masquerading as a script and incomplete requests are recorded as issues.

With Runtime/Debugger enabled, the collector also asks for source strings of
scripts compiled in allowed-origin default-world page contexts. This can inventory
inline or eval-generated JavaScript when a simple HTML `<script src>` scan misses
it. It does not patch `eval`, change game functions, bypass integrity checks, hide
DevTools or defeat anti-debugging. Attaching DevTools can itself alter behavior;
a game rejection is a blocker, not something the tool suppresses.

**A compiled-source snapshot is not automatically a standalone input.** It may
belong to an eval scope, inline script, module or distinct frame. Records retain
context/frame IDs, URLs and source positions. Neither network order nor script
compilation order establishes valid global execution order. Do not blindly feed
every captured snapshot or advertisement into `zero`.

Fidelity labels distinguish base64-decoded entity bytes, text bodies reencoded as
UTF-8, and compiled-source strings reencoded as UTF-8. None is called original
compressed HTTP wire data. Encodings/scopes must be established before any claim
of exact unchanged-original-game execution. Capture metadata always says that
Krunker has not been verified by this tool inside the native host.

The collector is page-target-only: workers and out-of-process iframes are not
captured. CSS, fonts, generic API JSON, WebSocket traffic and authentication flows
are not captured. Thus a successful capture is an inventory, **not everything a
complete playable client needs**.

## Validation and the observed blocker

16 unit cases cover permitted origins, private debugger endpoints, body fidelity,
input filtering, hashes, secret-header omission, compiled-source scope, incomplete
requests and repeated finalization. They use independent fixture messages, not a
live game.

The real-browser fixture test starts an HTTP server on literal localhost, attempts
to capture known HTML/JS/eval/Wasm bytes and would execute the unchanged captured
classic script in the standalone V8 host. Run it separately:

```sh
python3 tools/test_capture_integration.py --browser /path/to/chromium
```

For an isolated CI fixture only, `--unsafe-test-no-sandbox` is available. The test
serves only its own known loopback fixture. The acquisition CLI rejects that flag
for remote/non-loopback origins. Do not use it to browse the real game or other
untrusted content. Browser administration policies are never modified.

Observed here: DevTools connection succeeded; navigation returned
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. Zero script/response bodies were obtained.
`reports/capture-integration.json` records **blocked**, and the test exits **2**,
not 0. No localhost round trip or live game capture is credited as passed.

The older direct HTTPS and offline HAR-with-response-contents tools remain
available in `tools/capture.py`. Their synthetic acquisition tests do not establish
that the new live browser route or current original-game acquisition succeeded.

## Primary protocol references

- https://chromedevtools.github.io/devtools-protocol/tot/Network/
- https://chromedevtools.github.io/devtools-protocol/tot/Debugger/
- https://chromedevtools.github.io/devtools-protocol/tot/Runtime/

No browser executable is bundled or linked by this repository.
