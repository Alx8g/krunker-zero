import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
inspector=load('inspect_bootstrap')
probe=load('probe')
class InspectorTests(unittest.TestCase):
    def parse(self, html):
        parser=inspector.Scripts('https://example.test/game/index.html')
        parser.feed(html)
        parser.close()
        return parser
    def test_relative_src(self):
        p=self.parse('<script src="client.js"></script>')
        self.assertEqual(p.entries[0]['src'],'https://example.test/game/client.js')
    def test_script_flags(self):
        p=self.parse('<script type="module" async defer nomodule src="/a.js"></script>')
        self.assertTrue(p.entries[0]['async_attribute'])
        self.assertTrue(p.entries[0]['defer_attribute'])
        self.assertTrue(p.entries[0]['nomodule'])
        self.assertEqual(p.entries[0]['type'],'module')
    def test_inline_hash_without_source(self):
        p=self.parse('<script>let x="&amp;";</script>')
        self.assertEqual(p.entries[0]['inline_sha256'],hashlib.sha256(b'let x="&amp;";').hexdigest())
        self.assertNotIn('source',p.entries[0])
    def test_first_base_only(self):
        p=self.parse('<base href="/assets/"><base href="/wrong/"><script src="a.js"></script>')
        self.assertEqual(p.entries[0]['src'],'https://example.test/assets/a.js')
    def test_comments_not_scripts(self):
        p=self.parse('<!-- <script src="wrong"></script> --><script src="right"></script>')
        self.assertEqual(len(p.entries),1)
    def test_unterminated_marked(self):
        p=self.parse('<script>hello')
        self.assertIsNotNone(p.current)
class ProbeInputTests(unittest.TestCase):
    def test_bytes_hashed_without_rewriting(self):
        (ROOT/'build').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            p=Path(tmp)/'test.js'
            raw=b'\xef\xbb\xbfconst x = 1;\r\n'
            p.write_bytes(raw)
            actual,meta=probe.read_input(p)
            self.assertEqual(actual,raw)
            self.assertEqual(meta['sha256'],hashlib.sha256(raw).hexdigest())
    def test_html_is_not_a_bundle(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            p=Path(tmp)/'test.js'
            p.write_text('<!doctype html><html>not JS</html>')
            with self.assertRaises(ValueError): probe.read_input(p)
    def test_invalid_utf8_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'build') as tmp:
            p=Path(tmp)/'test.js'
            p.write_bytes(b'\xff\xff')
            with self.assertRaises(UnicodeDecodeError): probe.read_input(p)
if __name__=='__main__': unittest.main()
