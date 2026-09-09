"""Synthetic audit decision tests; no Windows execution is claimed."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from audit_windows import evaluate_run


class AuditGateTests(unittest.TestCase):
    def setUp(self):
        self.args=dict(host='C:/KZ/zero.exe',
                       paths=['C:/KZ/zero.exe','C:/KZ/libEGL.dll','C:/KZ/libGLESv2.dll'],
                       imports=['KERNEL32.dll'],graphics=True,backend='d3d11',
                       engine=dict(host='standalone',platform='windows-x64',engine='V8'),
                       native=dict(status='completed',exit_code=0,
                                   graphics=dict(backend='angle-d3d11-pbuffer',contexts=1,devices=[{'renderer':'fixture'}])),
                       snapshots=2)

    def result(self, **changes):
        values=copy.deepcopy(self.args);values.update(changes)
        return evaluate_run(**values)

    def test_valid_decision_data(self):self.assertTrue(self.result()['passed'])

    def test_pe_declarations_do_not_replace_loaded_angle(self):
        result=self.result(paths=['C:/KZ/zero.exe'],imports=['libEGL.dll','libGLESv2.dll'])
        self.assertFalse(result['passed'])

    def test_wrong_directory_angle_is_rejected(self):
        result=self.result(paths=['C:/KZ/zero.exe','C:/other/libEGL.dll','C:/KZ/libGLESv2.dll'])
        self.assertFalse(result['passed']);self.assertEqual(len(result['nonlocal_angle_modules']),1)

    def test_path_case_and_separators_are_windows_normalized(self):
        self.assertTrue(self.result(paths=[r'c:\kz\ZERO.EXE',r'c:\kz\LIBEGL.DLL',r'c:\kz\libGLESv2.dll'])['passed'])

    def test_wrong_own_child_executable_is_rejected(self):
        self.assertFalse(self.result(host='C:/other/zero.exe')['passed'])

    def test_no_complete_snapshot_is_rejected(self):
        self.assertFalse(self.result(snapshots=0)['passed'])

    def test_backend_substitution_is_rejected(self):
        self.assertFalse(self.result(backend='warp')['passed'])

    def test_explicit_warp_report_accepted(self):
        native=copy.deepcopy(self.args['native']);native['graphics']['backend']='angle-warp-pbuffer'
        self.assertTrue(self.result(backend='warp',native=native)['passed'])

    def test_missing_context_is_rejected(self):
        native=copy.deepcopy(self.args['native']);native['graphics']['contexts']=0
        self.assertFalse(self.result(native=native)['passed'])

    def test_invalid_context_count_is_rejected(self):
        native=copy.deepcopy(self.args['native']);native['graphics']['contexts']='1'
        self.assertFalse(self.result(native=native)['passed'])

    def test_missing_device_is_rejected(self):
        native=copy.deepcopy(self.args['native']);native['graphics']['devices']=[]
        self.assertFalse(self.result(native=native)['passed'])

    def test_engine_identity_is_required(self):
        self.assertFalse(self.result(engine={})['passed'])

    def test_native_error_is_rejected(self):
        self.assertFalse(self.result(native={'status':'script_exception','exit_code':1})['passed'])

    def test_forbidden_direct_import_is_rejected(self):
        self.assertFalse(self.result(imports=['libcef.dll'])['passed'])

    def test_graphics_free_runtime_remains_valid(self):
        self.assertTrue(self.result(paths=['C:/KZ/zero.exe','C:/Windows/System32/kernel32.dll'],
                                   graphics=False,native={'status':'completed','exit_code':0})['passed'])

    def test_core_must_not_import_angle(self):
        self.assertFalse(self.result(paths=['C:/KZ/zero.exe'], imports=['libEGL.dll'],
                                     graphics=False, native={'status':'completed','exit_code':0})['passed'])

    def test_malformed_graphics_report_rejected(self):
        native={'status':'completed','exit_code':0,'graphics':None}
        self.assertFalse(self.result(native=native)['passed'])

    def test_core_must_not_load_angle(self):self.assertFalse(self.result(graphics=False)['passed'])


if __name__=='__main__':unittest.main()
