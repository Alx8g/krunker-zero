import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import bootstrap_v8 as sdk
import capture


def tar_bytes(name='SDK/include/v8.h', data=b'header', kind=tarfile.REGTYPE):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as ar:
        entry=tarfile.TarInfo(name)
        entry.type=kind
        entry.linkname='outside' if kind in (tarfile.SYMTYPE,tarfile.LNKTYPE) else ''
        entry.size=len(data) if kind==tarfile.REGTYPE else 0
        ar.addfile(entry,io.BytesIO(data) if entry.size else None)
    return buf.getvalue()


class ArchiveTests(unittest.TestCase):
    def test_digest(self):
        self.assertEqual(sdk.checked_digest(b'a',hashlib.sha256(b'a').hexdigest()),hashlib.sha256(b'a').hexdigest())
    def test_bad_digest(self):
        with self.assertRaises(ValueError): sdk.checked_digest(b'a','0'*64)
    def test_release_unwrap(self):
        raw=tar_bytes()
        self.assertEqual(sdk.unwrap(raw,{'archive_sha256':hashlib.sha256(raw).hexdigest()}),raw)
    def test_artifact_unwrap(self):
        raw=tar_bytes(); buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z: z.writestr('sdk.tar.gz',raw)
        zipped=buf.getvalue()
        lock={'artifact_zip_sha256':hashlib.sha256(zipped).hexdigest(),'archive_name':'sdk.tar.gz','archive_sha256':hashlib.sha256(raw).hexdigest()}
        self.assertEqual(sdk.unwrap(zipped,lock),raw)
    def test_extra_zip_member(self):
        raw=tar_bytes(); buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('sdk.tar.gz',raw);z.writestr('surprise','x')
        with self.assertRaises(ValueError): sdk.unwrap(buf.getvalue(),{'artifact_zip_sha256':hashlib.sha256(buf.getvalue()).hexdigest(),'archive_name':'sdk.tar.gz'})
    def test_safe_extract(self):
        with tempfile.TemporaryDirectory() as d:
            sdk.extract_verified_tar(tar_bytes(),Path(d),'SDK')
            self.assertEqual((Path(d)/'SDK/include/v8.h').read_bytes(),b'header')
    def test_unsafe_paths(self):
        for name in ('../out','SDK/../out','/SDK/out','other/out','SDK\\out','SDK/C:bad'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError): sdk.extract_verified_tar(tar_bytes(name),Path(d),'SDK')
                self.assertEqual(list(Path(d).iterdir()),[])
    def test_links_and_devices(self):
        for kind in (tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.FIFOTYPE):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError): sdk.extract_verified_tar(tar_bytes(kind=kind),Path(d),'SDK')
    def test_nonempty_destination(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'preserve').write_text('yes')
            with self.assertRaises(ValueError): sdk.extract_verified_tar(tar_bytes(),Path(d),'SDK')
    def test_duplicate_member(self):
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as ar:
            for _ in range(2):
                e=tarfile.TarInfo('SDK/dup');e.size=1;ar.addfile(e,io.BytesIO(b'x'))
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):sdk.extract_verified_tar(buf.getvalue(),Path(d),'SDK')

    def fake_sdk(self):
        buf=io.BytesIO()
        with tarfile.open(fileobj=buf,mode='w:gz') as ar:
            for name in ('include/v8.h','include/v8-gn.h','include/v8-version.h','lib/libv8_monolith.a','lic/LICENSE'):
                raw=b'!<arch>\n' if name.endswith('.a') else b'synthetic SDK fixture'
                e=tarfile.TarInfo('SDK/'+name);e.size=len(raw);ar.addfile(e,io.BytesIO(raw))
        raw=buf.getvalue()
        return raw,dict(prefix='SDK',archive_sha256=hashlib.sha256(raw).hexdigest())
    def test_idempotent_verified_sdk(self):
        raw,lock=self.fake_sdk()
        with tempfile.TemporaryDirectory() as d:
            a=sdk.install(raw,lock,Path(d));b=sdk.install(raw,lock,Path(d))
            self.assertEqual(a,b)
    def test_changed_sdk_not_reused(self):
        raw,lock=self.fake_sdk()
        with tempfile.TemporaryDirectory() as d:
            dest=sdk.install(raw,lock,Path(d));(dest/'include/v8.h').write_text('changed')
            with self.assertRaises(ValueError):sdk.install(raw,lock,Path(d))
    def test_incomplete_sdk_rejected(self):
        raw=tar_bytes();lock=dict(prefix='SDK',archive_sha256=hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):sdk.install(raw,lock,Path(d))
            self.assertFalse((Path(d)/'SDK').exists())


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cap=capture.Capture(Path(self.tmp.name)/'capture','https://example.test/',{'https://example.test'})
    def entry(self,body='document.createElement("canvas")',url='https://example.test/game.js',**extra):
        e={'request':{'method':'GET','url':url,'headers':[{'name':'Authorization','value':'SECRET'}],'cookies':[{'name':'SID','value':'COOKIE_SECRET'}]},
           'response':{'status':200,'content':{'mimeType':'application/javascript','text':body}}}
        e['response']['content'].update(extra)
        return e
    def load(self,entries):
        capture.import_har(self.cap,{'log':{'entries':entries}})
        return self.cap.finish()
    def test_base64_bytes(self):
        raw=b'\xef\xbb\xbfconst x=1;\r\n'
        body,fidelity=capture.har_body({'text':base64.b64encode(raw).decode(),'encoding':'base64'})
        self.assertEqual(body,raw);self.assertIn('base64',fidelity)
    def test_text_fidelity_marked(self):
        raw,fidelity=capture.har_body({'text':'hello 🎮'})
        self.assertEqual(raw,'hello 🎮'.encode());self.assertIn('not_wire_bytes',fidelity)
    def test_missing_and_invalid_body(self):
        for c in ({},{'text':None},{'text':'bad!','encoding':'base64'},{'text':'x','encoding':'gzip'}):
            with self.subTest(c=c),self.assertRaises(ValueError):capture.har_body(c)
    def test_credentials_not_imported(self):
        result=self.load([self.entry()])
        self.assertEqual(len(result['records']),1)
        self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('Authorization',json.dumps(result))
    def test_disallowed_origin(self):
        result=self.load([self.entry(url='https://other.test/game.js')])
        self.assertEqual(result['records'],[])
    def test_post_not_imported(self):
        e=self.entry();e['request']['method']='POST'
        self.assertEqual(self.load([e])['records'],[])
    def test_error_status_not_imported(self):
        e=self.entry();e['response']['status']=403
        r=self.load([e]);self.assertEqual(r['records'],[]);self.assertEqual(len(r['issues']),1)
    def test_response_missing_detected(self):
        e=self.entry();del e['response']['content']['text']
        r=self.load([e]);self.assertEqual(r['records'],[]);self.assertEqual(len(r['issues']),1)
    def test_html_challenge_rejected(self):
        r=self.load([self.entry('\ufeff<!doctype html><html>challenge</html>')])
        self.assertEqual(r['records'],[]);self.assertEqual(len(r['issues']),1)
    def test_duplicate_deduped(self):
        self.assertEqual(len(self.load([self.entry(),self.entry()])['records']),1)
    def test_conflicting_bodies_preserved_and_flagged(self):
        r=self.load([self.entry('one'),self.entry('two')]);self.assertEqual(len(r['records']),2)
        self.assertEqual(r['issues'][0]['kind'],'conflicting_response_bodies')
    def test_original_body_hash(self):
        e=self.entry('const x=2;\r\n');r=self.load([e]);rec=r['records'][0]
        raw=(self.cap.out/rec['path']).read_bytes()
        self.assertEqual(raw,b'const x=2;\r\n');self.assertEqual(rec['sha256'],hashlib.sha256(raw).hexdigest())
    def test_origins(self):
        self.assertEqual(capture.origin('https://EXAMPLE.test:443/path'),'https://example.test')
        for u in ('http://example.test','file:///etc/passwd','https://user:pass@example.test','https://example.test:bad'):
            with self.subTest(u=u),self.assertRaises(ValueError):capture.origin(u)
    def test_redirect_blocked(self):
        redirect=capture.AllowedRedirect({'https://example.test'})
        with self.assertRaises(ValueError):redirect.redirect_request(None,None,302,'',{},'https://other.test/a')
    def test_live_capture_injected_transport(self):
        html=b'<script src="/game.js" defer></script><script src="https://other.test/ad.js"></script>'
        requests=[]
        def get(url,allowed):
            requests.append(url)
            return (html,url,'text/html') if url.endswith('/') else (b'window.start();',url,'application/javascript')
        capture.capture_live(self.cap,get)
        r=self.cap.finish()
        self.assertEqual(len(requests),2);self.assertEqual(len(r['records']),2)
        self.assertEqual(len(r['issues']),1)
        self.assertTrue(r['bootstrap_inventory']['scripts'][0]['defer_attribute'])
        self.assertFalse(r['game_executed'])
    def test_existing_directory_refused(self):
        with self.assertRaises(FileExistsError):capture.Capture(self.cap.out,self.cap.page,self.cap.allowed)

    def test_malformed_har_rejected(self):
        for data in ([],{}, {'log':[]},{'log':{'entries':[None]}}, {'log':{'entries':[{'request':None}]}}):
            with self.subTest(data=data),self.assertRaises(ValueError):capture.import_har(self.cap,data)
    def test_html_mime_not_imported_as_js(self):
        e=self.entry('Access denied',mimeType='text/html')
        r=self.load([e]);self.assertEqual(r['records'],[]);self.assertEqual(len(r['issues']),1)

if __name__=='__main__':unittest.main()
