#!/usr/bin/env python3
"""Acquire original bootstrap/script inputs; NEVER execute or patch them.
Use ordinary HTTPS GETs, or import response bodies from an authorized HAR capture.
Cookies, authorization headers, POST data and non-script assets are not copied.
"""
from __future__ import annotations
import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import sys
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from inspect_bootstrap import Scripts

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 16 * 1024 * 1024
MAX_HAR = 128 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_REQUESTS = 64
JS_TYPES = {'classic', '', 'text/javascript', 'application/javascript', 'application/ecmascript', 'text/ecmascript', 'module'}


def origin(url: str) -> str:
    p = urlsplit(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password:
        raise ValueError('Only HTTPS URLs without embedded credentials are accepted')
    port = p.port or 443
    host = p.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    return 'https://' + host + (':' + str(port) if port != 443 else '')


def without_fragment(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def body_kind(url: str, mime: str) -> str | None:
    mime = mime.partition(';')[0].strip().lower()
    if mime in JS_TYPES - {'classic', '', 'module'} or urlsplit(url).path.endswith(('.js', '.mjs')):
        return 'js'
    if mime == 'text/html':
        return 'html'
    return None


def validate_body(raw: bytes, kind: str) -> None:
    if len(raw) > MAX_BODY:
        raise ValueError('body exceeds 16 MiB')
    text = raw.decode('utf-8-sig')
    if kind == 'js' and text.lstrip().lower().startswith(('<!doctype html', '<html')):
        raise ValueError('HTML challenge/error page is not a JavaScript bundle')


class Capture:
    def __init__(self, out: Path, page: str, allowed: set[str]):
        self.out = out
        self.page = without_fragment(page)
        self.allowed = allowed
        self.total = 0
        self.records = []
        self.problems = []
        self.inventory = None
        out.mkdir(parents=True, exist_ok=False)
        out.chmod(0o700)

    def save(self, url: str, raw: bytes, kind: str, fidelity: str, **metadata) -> dict:
        if origin(url) not in self.allowed:
            raise ValueError('origin not permitted')
        validate_body(raw, kind)
        if self.total + len(raw) > MAX_TOTAL or len(self.records) >= 512:
            raise ValueError('capture storage cap exceeded')
        digest = hashlib.sha256(raw).hexdigest()
        name = f'{len(self.records):03d}-{digest[:16]}.{kind}'
        path = self.out/name
        with path.open('xb') as f:
            f.write(raw)
        path.chmod(0o600)
        self.total += len(raw)
        record = dict(url=without_fragment(url), path=name, kind=kind, bytes=len(raw),
                      sha256=digest, fidelity=fidelity, **metadata)
        self.records.append(record)
        if kind == 'html' and without_fragment(url) == self.page:
            parsed = Scripts(self.page)
            parsed.feed(raw.decode('utf-8-sig'))
            parsed.close()
            self.inventory = dict(scripts=parsed.entries, unfinished_script=parsed.current is not None)
        return record

    def finish(self) -> dict:
        result = dict(schema=1, page=self.page, records=self.records,
                      issues=self.problems, bootstrap_inventory=self.inventory,
                      game_executed=False, bytes_saved=self.total,
                      warning='This is an input inventory, NOT runtime execution order or a compatibility result. '
                              'URLs and bodies can still be sensitive; keep input/ private and out of Git. '
                              'HAR text is re-encoded UTF-8, not guaranteed original response bytes.')
        path = self.out/'capture.json'
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        path.chmod(0o600)
        return result


class AllowedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed: set[str]):
        self.allowed = allowed
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if origin(newurl) not in self.allowed:
            raise ValueError('redirect to a non-allowed origin')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url: str, allowed: set[str]) -> tuple[bytes, str, str]:
    if origin(url) not in allowed:
        raise ValueError('origin not permitted')
    req = urllib.request.Request(url, headers={'User-Agent': 'krunker-zero-input-capture/1', 'Accept-Encoding': 'identity'})
    with urllib.request.build_opener(AllowedRedirect(allowed)).open(req, timeout=15) as response:
        if response.status != 200:
            raise ValueError(f'HTTP {response.status}; only complete 200 responses accepted')
        if response.headers.get('Content-Encoding', 'identity').lower() not in ('', 'identity'):
            raise ValueError('server ignored identity encoding; use a HAR body export')
        raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError('response too large')
        charset = response.headers.get_content_charset()
        if charset and charset.lower() not in ('utf-8', 'utf8', 'us-ascii'):
            raise ValueError('non-UTF-8 response; preserve through an explicit import instead')
        return raw, response.geturl(), response.headers.get_content_type()


def capture_live(cap: Capture, get=fetch) -> None:
    raw, final, mime = get(cap.page, cap.allowed)
    if mime != 'text/html':
        raise ValueError('expected a bootstrap HTML response')
    cap.page = without_fragment(final)
    cap.save(final, raw, 'html', 'http_identity_response_bytes')
    seen = set()
    for entry in cap.inventory['scripts']:
        if entry['type'].lower() not in JS_TYPES:
            continue
        url = entry['src']
        if not url:
            # Retain the HTML itself, not a guessed inline-script transformation.
            continue
        url = without_fragment(url)
        if url in seen:
            continue
        seen.add(url)
        if len(seen) >= MAX_REQUESTS:
            cap.problems.append(dict(kind='request_limit', script_index=entry['index']))
            break
        try:
            if origin(url) not in cap.allowed:
                raise ValueError('origin not explicitly allowed')
            body, resolved, mime = get(url, cap.allowed)
            if mime == 'text/html':
                raise ValueError('HTML returned for a JavaScript resource')
            cap.save(resolved, body, 'js', 'http_identity_response_bytes',
                     requested_url=url, script_index=entry['index'])
        except (OSError, ValueError) as error:
            cap.problems.append(dict(url=url, kind='script_not_acquired', error=str(error)))


def har_body(content: dict) -> tuple[bytes, str]:
    text = content.get('text')
    if not isinstance(text, str):
        raise ValueError('HAR response body omitted; export with response contents')
    if len(text) > 2 * MAX_BODY:
        raise ValueError('HAR content too large')
    encoding = content.get('encoding')
    if encoding == 'base64':
        try:
            raw = base64.b64decode(text, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError('invalid base64 body') from error
        fidelity = 'har_base64_decoded_response_body'
    elif encoding in (None, ''):
        raw = text.encode('utf-8')
        fidelity = 'har_text_reencoded_utf8_not_wire_bytes'
    else:
        raise ValueError('unsupported HAR body encoding')
    if len(raw) > MAX_BODY:
        raise ValueError('HAR body too large')
    return raw, fidelity


def import_har(cap: Capture, data: dict) -> None:
    if not isinstance(data, dict) or not isinstance(data.get('log'), dict):
        raise ValueError('HAR must contain a log object')
    entries = data['log'].get('entries')
    if not isinstance(entries, list) or len(entries) > 10000:
        raise ValueError('invalid or excessively large HAR entry list')
    seen = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError('HAR entries must be objects')
        req, res = entry.get('request', {}), entry.get('response', {})
        if not isinstance(req, dict) or not isinstance(res, dict):
            raise ValueError('invalid HAR request/response object')
        url = req.get('url', '')
        if not isinstance(url, str):
            raise ValueError('HAR URL must be a string')
        if req.get('method') != 'GET':
            continue
        try:
            if origin(url) not in cap.allowed:
                continue
        except ValueError:
            continue
        content = res.get('content', {})
        if not isinstance(content, dict) or not isinstance(content.get('mimeType', ''), str):
            raise ValueError('invalid HAR content metadata')
        kind = body_kind(url, content.get('mimeType', ''))
        if kind is None or (kind == 'html' and without_fragment(url) != cap.page):
            continue
        try:
            if res.get('status') != 200:
                raise ValueError('HAR response is not a complete HTTP 200')
            if kind == 'js' and content.get('mimeType', '').partition(';')[0].strip().lower() == 'text/html':
                raise ValueError('HTML returned for a JavaScript resource')
            raw, fidelity = har_body(content)
            digest = hashlib.sha256(raw).hexdigest()
            key = without_fragment(url)
            if key in seen and digest != seen[key]:
                cap.problems.append(dict(kind='conflicting_response_bodies', url=key))
            if seen.get(key) == digest:
                continue
            seen[key] = digest
            cap.save(url, raw, kind, fidelity, har_entry=i)
        except (ValueError, UnicodeError) as error:
            cap.problems.append(dict(url=url, kind='body_not_imported', har_entry=i, error=str(error)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='https://krunker.io/')
    p.add_argument('--har', type=Path, help='Import saved response bodies without network access')
    p.add_argument('--allow-origin', action='append', default=[])
    p.add_argument('--out', type=Path, required=True, help='New directory under this repository input/')
    args = p.parse_args()
    try:
        out = args.out.resolve()
        if not out.is_relative_to((ROOT/'input').resolve()) or out == (ROOT/'input').resolve():
            raise ValueError('Capture destination must be a new directory below input/')
        cap = Capture(out, args.url, {origin(args.url), *(origin(u) for u in args.allow_origin)})
        if args.har:
            path = args.har.resolve(strict=True)
            if any(x.casefold() == 'wok' for x in path.parts):
                raise ValueError('excluded implementation path')
            if path.stat().st_size > MAX_HAR:
                raise ValueError('HAR file exceeds 128 MiB')
            import_har(cap, json.loads(path.read_text(encoding='utf-8-sig')))
        else:
            try:
                capture_live(cap)
            except (OSError, ValueError) as error:
                cap.problems.append(dict(kind='bootstrap_not_acquired', error=str(error)))
        result = cap.finish()
        print(f'Saved {len(result["records"])} bodies; {len(result["issues"])} issues. No game code executed.')
        print(out/'capture.json')
        return 0 if result['records'] and not result['issues'] else 2
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'capture failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
