#!/usr/bin/env python3
"""Development-only acquisition through a fresh local Chromium/Chrome profile.

Captures network entity bodies and compiled-source snapshots using the public
DevTools protocol. Does NOT patch game scripts, hide the debugger, bypass checks,
reuse a logged-in profile, or provide a browser fallback to the native runtime.
Snapshots are inventories, NOT an inferred execution/replay order.
"""
from __future__ import annotations
import argparse
import base64
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 16 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024
MAX_ENTRIES = 4096


def allowed_origin(url: str, allow_loopback_http: bool = False) -> str:
    p = urlsplit(url)
    if not p.hostname or p.username or p.password:
        raise ValueError('URL must have a host and no embedded credentials')
    is_local = p.hostname in ('127.0.0.1', '::1')
    if p.scheme != 'https' and not (p.scheme == 'http' and is_local and allow_loopback_http):
        raise ValueError('Only HTTPS or explicitly enabled loopback HTTP fixtures are accepted')
    port = p.port or (443 if p.scheme == 'https' else 80)
    host = '[' + p.hostname.lower() + ']' if ':' in p.hostname else p.hostname.lower()
    default = 443 if p.scheme == 'https' else 80
    return p.scheme + '://' + host + (':' + str(port) if port != default else '')


def local_debugger(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != 'ws' or p.hostname not in ('127.0.0.1', '::1') or p.username or p.password or not p.port:
        raise ValueError('DevTools endpoint must be a literal loopback ws:// address')
    return url


class CDP:
    def __init__(self, url: str):
        try:
            import websocket
        except ImportError as e:
            raise RuntimeError('Development capture requires websocket-client; see docs/CAPTURE.md') from e
        try:
            self.ws = websocket.create_connection(local_debugger(url), timeout=3, suppress_origin=True, http_no_proxy=['127.0.0.1','::1'])
        except websocket.WebSocketException as e:
            raise RuntimeError('DevTools connection failed: '+str(e)) from e
        self.websocket = websocket
        self.sequence = 0
        self.events = deque()

    def receive(self, deadline: float) -> dict:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('DevTools deadline reached')
        self.ws.settimeout(min(remaining, 3))
        try:
            raw = self.ws.recv()
        except self.websocket.WebSocketTimeoutException as e:
            raise TimeoutError('DevTools receive timed out') from e
        except self.websocket.WebSocketException as e:
            raise RuntimeError('DevTools receive failed: '+str(e)) from e
        if not raw or len(raw) > MAX_BODY * 4:
            raise ValueError('Empty or oversized DevTools message')
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError('Invalid DevTools message')
        return obj

    def command(self, method: str, params: dict | None = None, timeout: float = 5) -> dict:
        self.sequence += 1
        seq = self.sequence
        try:
            self.ws.send(json.dumps(dict(id=seq, method=method, params=params or {})))
        except self.websocket.WebSocketException as e:
            raise RuntimeError('DevTools send failed: '+str(e)) from e
        deadline = time.monotonic() + timeout
        while True:
            obj = self.receive(deadline)
            if obj.get('id') == seq:
                if 'error' in obj:
                    raise RuntimeError('DevTools ' + method + ': ' + str(obj['error'].get('message', 'error')))
                result = obj.get('result', {})
                if not isinstance(result, dict):
                    raise ValueError('Invalid DevTools result')
                return result
            if 'method' in obj:
                if len(self.events) >= MAX_ENTRIES * 8:
                    raise RuntimeError('DevTools event queue cap exceeded')
                self.events.append(obj)
            # A response to an earlier timed-out command is ignored, not treated
            # as the result of this command. Request ids are never reused.

    def event(self, deadline: float) -> dict:
        if self.events:
            return self.events.popleft()
        while True:
            obj = self.receive(deadline)
            if 'method' in obj:
                return obj

    def close(self):
        self.ws.close()


def decode_body(result: dict) -> tuple[bytes, str]:
    text = result.get('body')
    if not isinstance(text, str) or len(text) > MAX_BODY * 2:
        raise ValueError('Missing or oversized response body')
    encoded = result.get('base64Encoded', False)
    if not isinstance(encoded, bool):
        raise ValueError('base64Encoded must be boolean')
    if encoded:
        raw = base64.b64decode(text, validate=True)
        fidelity = 'cdp_base64_decoded_entity_body_not_compressed_wire_bytes'
    else:
        raw = text.encode('utf-8')
        fidelity = 'cdp_text_reencoded_utf8_not_wire_bytes'
    if len(raw) > MAX_BODY:
        raise ValueError('Body exceeds 16 MiB')
    return raw, fidelity


def resource_kind(url: str, mime: str, resource_type: str) -> str | None:
    mime = mime.split(';')[0].strip().lower()
    suffix = urlsplit(url).path.lower()
    if mime == 'text/html' and resource_type == 'Document': return 'html'
    if resource_type == 'Script' and mime != 'text/html': return 'js'
    if mime in ('application/javascript', 'text/javascript', 'application/ecmascript'): return 'js'
    if mime == 'application/wasm' or suffix.endswith('.wasm'): return 'wasm'
    if mime.startswith('image/') and mime != 'image/svg+xml': return 'image'
    if mime.startswith('audio/'): return 'audio'
    return None


class Recorder:
    def __init__(self, output: Path, page: str, origins: set[str], local_http: bool = False):
        self.output, self.page, self.origins, self.local_http = output, page, origins, local_http
        output.mkdir(parents=True, exist_ok=False);output.chmod(0o700)
        self.records, self.sources, self.issues = [], [], []
        self.pending, self.requests, self.contexts = {}, {}, {}
        self.saved = {};self.total = 0;self.ignored_responses = 0;self.loads = 0
        self.finished_result = None
        self.primary_document_received = False
        self.event_count = 0

    def permitted(self, url: str) -> bool:
        try: return allowed_origin(url, self.local_http) in self.origins
        except ValueError: return False

    def write(self, data: bytes, extension: str) -> dict:
        if len(data) > MAX_BODY: raise ValueError('16 MiB body cap exceeded')
        sha = hashlib.sha256(data).hexdigest()
        key = (sha, extension)
        if key in self.saved: return self.saved[key].copy()
        if len(self.saved) >= MAX_ENTRIES or self.total + len(data) > MAX_TOTAL:
            raise ValueError('Capture storage cap exceeded')
        name = sha + '.' + extension
        path = self.output/name
        with path.open('xb') as f: f.write(data)
        path.chmod(0o600)
        result = dict(path=name, bytes=len(data), sha256=sha)
        self.saved[key] = result;self.total += len(data)
        return result.copy()

    def event(self, client, event: dict):
        self.event_count += 1
        if self.event_count > MAX_ENTRIES * 32:
            raise ValueError('Capture event cap exceeded')
        method, p = event.get('method'), event.get('params', {})
        if method == 'Runtime.executionContextCreated':
            c = p['context']
            if len(self.contexts) >= MAX_ENTRIES: raise ValueError('Execution context cap exceeded')
            self.contexts[c['id']] = dict(origin=c.get('origin', ''), aux=c.get('auxData', {}))
        elif method == 'Runtime.executionContextDestroyed':
            self.contexts.pop(p.get('executionContextId'), None)
        elif method == 'Runtime.executionContextsCleared':
            self.contexts.clear()
        elif method == 'Page.loadEventFired': self.loads += 1
        elif method == 'Network.requestWillBeSent':
            r = p.get('request', {})
            if len(self.requests) >= MAX_ENTRIES: raise ValueError('Request cap exceeded')
            # Intentionally never retain cookies, auth headers or POST data.
            self.requests[p['requestId']] = dict(method=r.get('method'), url=r.get('url', ''))
        elif method == 'Network.responseReceived':
            r = p['response'];url = r.get('url', '');mime = r.get('mimeType', '')
            kind = resource_kind(url, mime, p.get('type', ''))
            req = self.requests.get(p['requestId'], {})
            if p.get('type') == 'Script' and mime.split(';')[0].strip().lower() == 'text/html' and self.permitted(url):
                self.issues.append(dict(kind='html_instead_of_script',url=url))
            if kind and self.permitted(url) and req.get('method') == 'GET':
                self.pending[p['requestId']] = dict(url=url, mime=mime, kind=kind,
                    status=r.get('status'), resource_type=p.get('type'), frame_id=p.get('frameId'),
                    from_service_worker=bool(r.get('fromServiceWorker')), from_disk_cache=bool(r.get('fromDiskCache')))
            else: self.ignored_responses += 1
        elif method == 'Network.loadingFinished':
            rid = p['requestId'];r = self.pending.pop(rid, None);self.requests.pop(rid, None)
            if not r: return
            try:
                if r['status'] != 200: raise ValueError('Response is not complete HTTP 200')
                body, fidelity = decode_body(client.command('Network.getResponseBody', {'requestId': rid}))
                if r['kind'] == 'js' and body.lstrip().lower().startswith((b'<html', b'<!doctype html')):
                    raise ValueError('HTML error/challenge body is not a script')
                record = dict(**r, **self.write(body, r['kind']), fidelity=fidelity)
                self.records.append(record)
                if r['kind'] == 'html' and r['url'].split('#')[0] == self.page.split('#')[0]:
                    self.primary_document_received = True
            except (OSError, RuntimeError, TimeoutError, ValueError) as e:
                self.issues.append(dict(kind='response_body_unavailable', url=r['url'], error=str(e)))
        elif method == 'Network.loadingFailed':
            rid = p.get('requestId');r = self.pending.pop(rid, None) or self.requests.get(rid, {})
            self.requests.pop(rid, None)
            if self.permitted(r.get('url', '')):
                self.issues.append(dict(kind='network_loading_failed', url=r.get('url'), error=p.get('errorText'), canceled=p.get('canceled', False)))
        elif method == 'Debugger.scriptParsed':
            ctx = self.contexts.get(p.get('executionContextId'), {})
            if not self.permitted(ctx.get('origin', '')) or not ctx.get('aux', {}).get('isDefault'): return
            if p.get('scriptLanguage', 'JavaScript') != 'JavaScript': return
            if len(self.sources) >= MAX_ENTRIES: raise ValueError('Compiled script cap exceeded')
            try:
                if p.get('length', 0) > MAX_BODY: raise ValueError('Compiled source exceeds size cap')
                source = client.command('Debugger.getScriptSource', {'scriptId': p['scriptId']}).get('scriptSource')
                if not isinstance(source, str): raise ValueError('Script source omitted')
                data = source.encode('utf-8')
                self.sources.append(dict(**self.write(data, 'js'), script_id=p['scriptId'],
                    url=p.get('url', ''), execution_context=p.get('executionContextId'),
                    context_origin=ctx['origin'], frame_id=ctx['aux'].get('frameId'),
                    start_line=p.get('startLine'), start_column=p.get('startColumn'),
                    end_line=p.get('endLine'), end_column=p.get('endColumn'), is_module=p.get('isModule', False),
                    source_url_directive=p.get('hasSourceURL', False),
                    fidelity='cdp_compiled_source_string_reencoded_utf8_not_network_bytes'))
            except (OSError, RuntimeError, TimeoutError, ValueError) as e:
                self.issues.append(dict(kind='compiled_source_unavailable', script_id=p.get('scriptId'), error=str(e)))

    def finish(self) -> dict:
        if self.finished_result is not None:
            return self.finished_result
        for rid, r in self.requests.items():
            if rid not in self.pending and r.get('method') == 'GET' and self.permitted(r.get('url', '')):
                self.issues.append(dict(kind='request_incomplete_at_capture_end',url=r['url']))
        for r in self.pending.values():
            self.issues.append(dict(kind='response_incomplete_at_capture_end', url=r['url']))
        result = dict(schema=1, page=self.page, capture_transport='local_browser_devtools',
            primary_document_received=self.primary_document_received, network_bodies=self.records,
            compiled_sources=self.sources, issues=self.issues, ignored_response_count=self.ignored_responses,
            load_events=self.loads, bytes_saved=self.total, runtime_execution_order_established=False,
            game_executed_by_zero=False, live_game_bootstrap_verified=False,
            limitations=['A capture is not a compatible runtime or proof of gameplay.',
                'Compiled scripts include inline/eval/module sources: do not blindly execute all snapshots.',
                'Workers and out-of-process iframe targets are not captured by this page-only collector.',
                'Only explicit origins and selected GET entity types are saved; no font files are captured.',
                'DevTools can affect game execution. No anti-debugging or integrity bypass is performed.',
                'URLs and response bodies can contain sensitive content; keep input/ private and out of Git.'])
        path=self.output/'browser-capture.json';path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');path.chmod(0o600)
        self.finished_result = result
        return result


class Browser:
    def __init__(self, executable: str, headless: bool, unsafe_no_sandbox: bool):
        self.executable, self.headless, self.unsafe = executable, headless, unsafe_no_sandbox
        self.temp = None;self.process = None;self.log = None

    def __enter__(self) -> str:
        self.temp=tempfile.TemporaryDirectory(prefix='zero-capture-profile-')
        folder=Path(self.temp.name);self.log=open(folder/'browser.log','wb')
        argv=[self.executable,'--user-data-dir='+str(folder),'--remote-debugging-port=0',
              '--no-first-run','--no-default-browser-check','--disable-background-networking',
              '--disable-dev-shm-usage','about:blank']
        if self.headless: argv.insert(1,'--headless')
        if self.unsafe:
            argv.insert(1,'--no-sandbox')
            argv.insert(1,'--disable-gpu')  # loopback-only script capture fixture, not game graphics
        try:
            self.process=subprocess.Popen(argv,stdout=self.log,stderr=self.log,start_new_session=os.name=='posix')
            deadline=time.monotonic()+15;active=folder/'DevToolsActivePort'
            while not active.exists():
                if self.process.poll() is not None: raise RuntimeError('Capture browser exited at startup; use a working local browser installation')
                if time.monotonic()>deadline: raise TimeoutError('Capture browser did not expose a DevTools port')
                time.sleep(.05)
            port=int(active.read_text().splitlines()[0])
            # Disable environment proxies for the literal-loopback management endpoint.
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f'http://127.0.0.1:{port}/json/list',timeout=3) as r:
                tabs=json.loads(r.read(1024*1024))
            page=next((x for x in tabs if x.get('type')=='page'),None)
            if not page: raise RuntimeError('No page target in fresh capture profile')
            return local_debugger(page['webSocketDebuggerUrl'])
        except BaseException:
            self.__exit__(None,None,None);raise

    def __exit__(self,*exc):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=3)
            if os.name=='posix':
                try:os.killpg(self.process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
        if self.log:self.log.close()
        if self.temp:self.temp.cleanup()


def capture(client: CDP, recorder: Recorder, seconds: float):
    client.command('Network.enable',dict(maxTotalBufferSize=MAX_TOTAL,maxResourceBufferSize=MAX_BODY))
    client.command('Runtime.enable');client.command('Debugger.enable');client.command('Page.enable')
    nav=client.command('Page.navigate',dict(url=recorder.page))
    if nav.get('errorText'):recorder.issues.append(dict(kind='navigation_failed',error=nav['errorText']))
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        try:recorder.event(client,client.event(deadline))
        except TimeoutError:continue
    # Drain events already received during commands; do not fetch forever after
    # the deadline. Responses still in flight are explicitly incomplete.
    drained=0
    while client.events and drained<MAX_ENTRIES and time.monotonic()<deadline+2:
        recorder.event(client,client.events.popleft());drained+=1


def browser_path(value: str | None) -> str:
    if value:return str(Path(value).resolve(strict=True))
    for name in ('chromium','chromium-browser','google-chrome','chrome','msedge'):
        if path:=shutil.which(name):return path
    for path in ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
                 os.environ.get('PROGRAMFILES','')+'/Google/Chrome/Application/chrome.exe',
                 os.environ.get('PROGRAMFILES(X86)','')+'/Microsoft/Edge/Application/msedge.exe']:
        if Path(path).is_file():return path
    raise ValueError('No capture browser found; supply --browser with its executable path')


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='https://krunker.io/');p.add_argument('--allow-origin',action='append',default=[])
    p.add_argument('--browser');p.add_argument('--headless',action='store_true');p.add_argument('--seconds',type=float,default=15)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--allow-loopback-http',action='store_true',help='Explicit synthetic fixture mode only')
    p.add_argument('--unsafe-test-no-sandbox',action='store_true',help='Untrusted browsing is unsafe; isolated CI fixture testing only')
    args=p.parse_args();recorder=None
    try:
        if not 1<=args.seconds<=120:raise ValueError('Capture duration must be 1..120 seconds')
        out=args.out.resolve();base=(ROOT/'input').resolve()
        if not out.is_relative_to(base) or out==base:raise ValueError('Output must be a new directory below input/')
        origins={allowed_origin(args.url,args.allow_loopback_http),*(allowed_origin(u,args.allow_loopback_http) for u in args.allow_origin)}
        recorder=Recorder(out,args.url,origins,args.allow_loopback_http)
        if args.unsafe_test_no_sandbox and not args.allow_loopback_http:
            raise ValueError('--unsafe-test-no-sandbox is restricted to literal-loopback HTTP fixture captures')
        if args.unsafe_test_no_sandbox and not all(x.startswith(('http://127.0.0.1:','http://[::1]:')) for x in origins):
            raise ValueError('Unsandboxed capture only accepts loopback fixture origins')
        with Browser(browser_path(args.browser),args.headless,args.unsafe_test_no_sandbox) as endpoint:
            client=CDP(endpoint)
            try:capture(client,recorder,args.seconds)
            finally:client.close()
    except (OSError,ValueError,RuntimeError,TimeoutError,StopIteration) as e:
        if recorder:recorder.issues.append(dict(kind='capture_failed',error=str(e)))
        else:print('Capture failed: '+str(e),file=sys.stderr);return 1
    result=recorder.finish()
    print(f"Saved {len(result['network_bodies'])} network bodies and {len(result['compiled_sources'])} compiled-source snapshots; {len(result['issues'])} issues.")
    print(out/'browser-capture.json')
    print('This capture has NOT been run in the native host.')
    return 0 if result['primary_document_received'] and result['compiled_sources'] and not result['issues'] else 2

if __name__=='__main__':raise SystemExit(main())
