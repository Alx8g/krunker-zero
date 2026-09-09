import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from capture_browser import Recorder, allowed_origin, local_debugger, decode_body, resource_kind

class Client:
    def __init__(self, replies):self.replies=replies;self.calls=[]
    def command(self, method, params):self.calls.append((method,params));return self.replies[method]

class CaptureTests(unittest.TestCase):
    def test_origin_rules(self):
        self.assertEqual(allowed_origin('https://krunker.io/game?q=1'),'https://krunker.io')
        for url in ['http://krunker.io/','https://user:pass@krunker.io/','file:///tmp/x','http://evil.example/']:
            with self.assertRaises(ValueError):allowed_origin(url,True)
        self.assertEqual(allowed_origin('http://127.0.0.1:8080/',True),'http://127.0.0.1:8080')
    def test_debugger_loopback_only(self):
        self.assertEqual(local_debugger('ws://127.0.0.1:123/devtools/page/a'),'ws://127.0.0.1:123/devtools/page/a')
        for u in ['ws://example.com:123/a','ws://127.0.0.1.evil.com:1/','wss://127.0.0.1:1/','ws://user@127.0.0.1:1/']:
            with self.assertRaises(ValueError):local_debugger(u)
    def test_body_fidelity(self):
        raw=b'\x00\xff\xfe\x80'
        out,kind=decode_body(dict(body=base64.b64encode(raw).decode(),base64Encoded=True))
        self.assertEqual(out,raw);self.assertIn('entity_body',kind)
        out,kind=decode_body(dict(body='héllo',base64Encoded=False))
        self.assertEqual(out,'héllo'.encode());self.assertIn('not_wire_bytes',kind)
    def test_invalid_body_rejected(self):
        for body in [{},{'body':'!','base64Encoded':True},{'body':'x','base64Encoded':'false'}]:
            with self.assertRaises(ValueError):decode_body(body)
    def test_kind_filter_no_fonts(self):
        self.assertIsNone(resource_kind('https://a/font.woff','font/woff','Font'))
        self.assertEqual(resource_kind('https://a/a.wasm','application/octet-stream','Fetch'),'wasm')
        self.assertIsNone(resource_kind('https://a/api','application/json','Fetch'))
    def recorder(self,folder):return Recorder(Path(folder)/'capture','https://krunker.io/',{'https://krunker.io'})
    def event(self,r,c,name,**params):r.event(c,dict(method=name,params=params))
    def request(self,r,c,url='https://krunker.io/game.js',method='GET',mime='text/javascript',kind='Script',status=200):
        self.event(r,c,'Network.requestWillBeSent',requestId='1',request=dict(url=url,method=method,headers={'Authorization':'secret'},postData='secret'))
        self.event(r,c,'Network.responseReceived',requestId='1',type=kind,response=dict(url=url,status=status,mimeType=mime,headers={'Set-Cookie':'secret'}))
    def test_network_hash_and_secret_omission(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({'Network.getResponseBody':{'body':'const answer=42;'}})
            self.request(r,c);self.event(r,c,'Network.loadingFinished',requestId='1')
            result=r.finish();self.assertEqual(result['network_bodies'][0]['sha256'],hashlib.sha256(b'const answer=42;').hexdigest())
            self.assertNotIn('secret',json.dumps(result));self.assertFalse(result['game_executed_by_zero'])
            self.assertEqual((r.output/result['network_bodies'][0]['path']).read_bytes(),b'const answer=42;')
    def test_post_and_foreign_origin_not_captured(self):
        for method,url in [('POST','https://krunker.io/game.js'),('GET','https://foreign.example/game.js')]:
            with tempfile.TemporaryDirectory() as folder:
                r=self.recorder(folder);c=Client({});self.request(r,c,url=url,method=method)
                self.event(r,c,'Network.loadingFinished',requestId='1');self.assertEqual(r.records,[]);self.assertEqual(c.calls,[])
    def test_http_failure_not_javascript(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({});self.request(r,c,status=403)
            self.event(r,c,'Network.loadingFinished',requestId='1');self.assertFalse(r.records);self.assertEqual(len(r.issues),1)
    def test_html_cannot_masquerade_as_javascript(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({'Network.getResponseBody':{'body':'<!doctype html><title>challenge</title>'}})
            self.request(r,c);self.event(r,c,'Network.loadingFinished',requestId='1');self.assertFalse(r.records);self.assertEqual(len(r.issues),1)
    def test_failed_loading_is_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({});self.request(r,c)
            self.event(r,c,'Network.loadingFailed',requestId='1',errorText='net::ERR_NAME_NOT_RESOLVED')
            self.assertIn('ERR_NAME_NOT_RESOLVED',r.finish()['issues'][0]['error'])
    def test_dynamic_source_keeps_scope_and_is_not_wire_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({'Debugger.getScriptSource':{'scriptSource':'var decoded=42;'}})
            self.event(r,c,'Runtime.executionContextCreated',context=dict(id=7,origin='https://krunker.io',auxData={'isDefault':True,'frameId':'A'}))
            self.event(r,c,'Debugger.scriptParsed',scriptId='9',executionContextId=7,url='',startLine=0,startColumn=0,isModule=False)
            result=r.finish();self.assertEqual(len(result['compiled_sources']),1)
            source=result['compiled_sources'][0];self.assertEqual(source['execution_context'],7);self.assertEqual(source['url'],'')
            self.assertIn('not_network_bytes',source['fidelity']);self.assertFalse(result['runtime_execution_order_established'])
    def test_extension_context_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({})
            self.event(r,c,'Runtime.executionContextCreated',context=dict(id=7,origin='chrome-extension://id',auxData={'isDefault':False}))
            self.event(r,c,'Debugger.scriptParsed',scriptId='9',executionContextId=7,url='https://krunker.io/fake.js')
            self.assertEqual(r.sources,[]);self.assertEqual(c.calls,[])
    def test_deduplication_preserves_source_records(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);a=r.write(b'42;','js');b=r.write(b'42;','js')
            self.assertEqual(a,b);self.assertEqual(r.total,3)
    def test_incomplete_response_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({});self.request(r,c)
            self.assertEqual(r.finish()['issues'][0]['kind'],'response_incomplete_at_capture_end')

    def test_pending_request_and_finish_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({})
            self.event(r,c,'Network.requestWillBeSent',requestId='unanswered',request=dict(url='https://krunker.io/game.js',method='GET'))
            a=r.finish();b=r.finish()
            self.assertEqual(a,b);self.assertEqual(len(a['issues']),1)
            self.assertEqual(a['issues'][0]['kind'],'request_incomplete_at_capture_end')
    def test_explicit_html_script_mime_is_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            r=self.recorder(folder);c=Client({});self.request(r,c,mime='text/html')
            self.event(r,c,'Network.loadingFinished',requestId='1')
            self.assertEqual(r.records,[]);self.assertEqual(c.calls,[])
            self.assertEqual(r.finish()['issues'][0]['kind'],'html_instead_of_script')

if __name__=='__main__':unittest.main()

