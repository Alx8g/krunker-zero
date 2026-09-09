#!/usr/bin/env python3
"""Try a real browser -> captured bytes -> native host round trip on localhost.

Independent fixtures only, no game or remote website is used. An environmental
browser policy block is a BLOCKED result and a nonzero exit, not a passing test.
The test never alters browser policy. All child processes are stopped on exit.
"""
from __future__ import annotations
import argparse
import hashlib
import http.server
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from capture_browser import Browser, CDP, Recorder, browser_path, capture

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=b'globalThis.sample = new Uint8Array([40, 2]);\nsetTimeout(() => { console.log("CAPTURE_NATIVE", sample[0] + sample[1]); }, 0);\n'
DYNAMIC=b'globalThis.dynamic = 42;'
HTML=b'<!doctype html><title>Independent capture fixture</title><script src="/original.js"></script><script>eval("globalThis.dynamic = 42;");fetch("/module.wasm");</script>'
WASM=bytes.fromhex('0061736d01000000')

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body,mime={'/':(HTML,'text/html'),'/original.js':(SCRIPT,'text/javascript'),
                   '/module.wasm':(WASM,'application/wasm')}.get(self.path,(b'','text/plain'))
        self.send_response(200);self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def log_message(self,*args):pass


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--browser');p.add_argument('--host',type=Path,default=ROOT/'build/standalone/zero')
    p.add_argument('--report',type=Path,default=ROOT/'reports/capture-integration.json')
    p.add_argument('--unsafe-test-no-sandbox',action='store_true',help='Only this known localhost fixture; never remote game capture')
    args=p.parse_args();result=dict(schema=1,scope='Independent localhost HTTP fixture, NOT Krunker',
                                  devtools_connected=False,capture_to_native_passed=False,status='failed')
    try:
        browser=browser_path(args.browser);host=args.host.resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix='zero-capture-test-') as temp:
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            url=f'http://127.0.0.1:{server.server_port}/'
            output=Path(temp)/'capture';rec=Recorder(output,url,{url[:-1]},True)
            try:
                with Browser(browser,True,args.unsafe_test_no_sandbox) as endpoint:
                    client=CDP(endpoint);result['devtools_connected']=True
                    try:capture(client,rec,2)
                    finally:client.close()
            finally:
                server.shutdown();server.server_close();thread.join()
                result['capture_report']=rec.finish()
            r=result['capture_report']
            if any('ERR_BLOCKED_BY_ADMINISTRATOR' in str(x.get('error','')) for x in r['issues']):
                result['status']='blocked'
                result['error']='Browser navigation blocked by administrator policy; policy was not changed.'
            elif not r['primary_document_received'] or r['issues']:
                result['error']='Browser capture did not supply a complete fixture document.'
            else:
                js=next(x for x in r['network_bodies'] if x['kind']=='js' and x['url'].endswith('/original.js'))
                actual=(output/js['path']).read_bytes()
                if actual != SCRIPT:raise ValueError('Network script bytes differ from served fixture')
                if not any((output/x['path']).read_bytes()==DYNAMIC for x in r['compiled_sources']):
                    raise ValueError('Dynamic compiled source missing')
                if not any(x['kind']=='wasm' and (output/x['path']).read_bytes()==WASM for x in r['network_bodies']):
                    raise ValueError('Wasm body missing or changed')
                cp=subprocess.run([str(host),'--profile','core',str(output/js['path'])],capture_output=True,text=True,timeout=10)
                nr=json.loads(cp.stdout);result['native_report']=nr
                if cp.returncode or nr['status']!='completed' or [x['text'] for x in nr['logs']]!=['CAPTURE_NATIVE 42']:
                    raise ValueError('Native execution of captured fixture did not pass')
                result.update(status='passed',capture_to_native_passed=True,
                              script_sha256=hashlib.sha256(actual).hexdigest(),compiled_dynamic_source_verified=True)
    except (OSError,ValueError,RuntimeError,StopIteration,subprocess.TimeoutExpired) as exc:
        result['error']=str(exc)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(result['status'].upper()+': '+str(result.get('error','byte-identical capture-to-native round trip')))
    print('Evidence: '+str(args.report))
    return 0 if result['status']=='passed' else 2 if result['status']=='blocked' else 1

if __name__=='__main__':raise SystemExit(main())
