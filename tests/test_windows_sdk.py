"""Pure prerequisite tests. Fixture files are not executable Windows SDKs."""
import copy
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
import windows_deps as deps
from windows_sdk import ANGLE_SDK, SDK_FILES, probe_source_sdks, require_source_sdks


class SDKPreflightTests(unittest.TestCase):
    def make_sdk(self, root):
        for template in SDK_FILES:
            p = root/template.format(version=ANGLE_SDK)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('UNIT-TEST SENTINEL, NOT AN SDK', encoding='utf-8')

    def test_missing_root_is_not_ready(self):
        self.assertFalse(probe_source_sdks('', deps.load_lock())['ready'])

    def test_env_directory_alone_is_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(probe_source_sdks(tmp, deps.load_lock())['ready'])

    def test_exact_version_with_all_required_files_is_ready(self):
        with tempfile.TemporaryDirectory(prefix='kz sdk ') as tmp:
            self.make_sdk(Path(tmp))
            self.assertTrue(probe_source_sdks(tmp, deps.load_lock())['ready'])

    def test_each_missing_component_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.make_sdk(root)
            for template in SDK_FILES:
                relative = template.format(version=ANGLE_SDK); p = root/relative
                p.unlink()
                result = probe_source_sdks(tmp, deps.load_lock())
                self.assertEqual(result['checks'][0]['missing_files'], [relative])
                p.write_text('UNIT-TEST SENTINEL')

    def test_different_version_does_not_satisfy_pin(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for template in SDK_FILES:
                p = root/template.format(version='10.0.26100.0')
                p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fixture')
            self.assertFalse(probe_source_sdks(tmp, deps.load_lock())['ready'])

    def test_changed_source_pin_requires_explicit_review(self):
        lock = copy.deepcopy(deps.load_lock()); lock['angle']['commit'] = '0'*40
        with self.assertRaisesRegex(ValueError, 'pin changed'):
            probe_source_sdks('', lock)

    def test_v8_only_does_not_require_angle_sdk(self):
        self.assertTrue(probe_source_sdks('', deps.load_lock(), ('v8',))['ready'])

    def test_existing_sdk_reuse_has_no_source_sdk_requirement(self):
        self.assertTrue(require_source_sdks('', deps.load_lock(), ())['ready'])

    def test_unknown_component_rejected(self):
        with self.assertRaises(ValueError):probe_source_sdks('', deps.load_lock(), ('other',))

    def test_all_preflight_fails_before_any_source_build(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(sys, 'argv', ['windows_deps.py', '--component', 'all', '--out', tmp+'/out']), \
             patch.object(deps, 'require_windows'), patch.object(deps, 'build') as build, \
             patch.dict(os.environ, {'WindowsSdkDir': tmp}), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(deps.main(), 1)
            build.assert_not_called()
            self.assertFalse((Path(tmp)/'out').exists())

    def test_sdk_validation_does_not_change_source_lock(self):
        before = deps.LOCK.read_bytes()
        probe_source_sdks('', deps.load_lock())
        self.assertEqual(deps.LOCK.read_bytes(), before)

    def test_verified_existing_destination_does_not_download(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(deps, 'require_windows'), patch.object(deps, 'doctor', return_value={'ready': True}), \
             patch.object(deps, 'verify_sdk') as verify, patch.object(deps, 'require_source_sdks') as preflight, \
             contextlib.redirect_stdout(io.StringIO()):
            deps.build('angle', Path(tmp)/'work', Path(tmp), deps.load_lock(), 1)
            verify.assert_called_once(); preflight.assert_not_called()


if __name__ == '__main__': unittest.main()
