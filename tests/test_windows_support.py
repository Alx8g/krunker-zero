"""Portable unit tests for Windows tooling; never Windows runtime validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import windows_deps as deps
from windows import build_command, package
from host_paths import backend_args, default_host
from audit_windows import evaluate, module_paths
from render_probe import frame_pixels
ROOT=Path(__file__).resolve().parents[1]


class WindowsSupportTests(unittest.TestCase):
    def setUp(self):
        self.lock=deps.load_lock()

    def make_sdk(self,root,component='v8'):
        for path in deps.required_paths(component):
            target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'FAKE UNIT-TEST FILE, NEVER AN SDK')
        deps.record_sdk(root,component,self.lock)

    def test_depot_build_wrappers_use_explicit_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for tool in ('gn', 'ninja'):
                script = root/(tool+'.py')
                script.write_text('# fixture')
                with patch.object(deps.shutil, 'which', return_value=str(root/(tool+'.bat'))), patch.object(deps, 'checked', return_value='ok') as run:
                    self.assertEqual(deps.checked_tool(tool, ['--version'], root, {'PATH': ''}), 'ok')
                    run.assert_called_once_with([sys.executable, str(script), '--version'], root, {'PATH': ''}, capture=False)

    def test_managed_git_launcher_reuse_and_modified_refusal(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(deps.shutil, 'which', return_value='C:/Program Files/Git/cmd/git.exe'):
            root = Path(tmp)
            directory = deps.prepare_git_launcher(root, {'PATH': 'installed'})
            launcher = directory/'git.bat'
            self.assertIn('"C:/Program Files/Git/cmd/git.exe" %*', launcher.read_text())
            self.assertEqual(directory, deps.prepare_git_launcher(root, {'PATH': 'installed'}))
            launcher.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Refusing modified'):
                deps.prepare_git_launcher(root, {'PATH': 'installed'})

    def test_managed_git_launcher_rejects_missing_or_unsafe_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            for executable in (None, 'C:/bad%PATH%/git.exe', 'C:/bad"/git.exe'):
                with patch.object(deps.shutil, 'which', return_value=executable):
                    with self.assertRaisesRegex(ValueError, 'safe installed'):
                        deps.prepare_git_launcher(Path(tmp), {'PATH': 'installed'})

    def test_all_sources_use_fixed_official_commits(self):
        for name in ('depot_tools','v8','angle'):
            self.assertEqual(len(self.lock[name]['commit']),40)
            self.assertTrue(self.lock[name]['url'].startswith('https://chromium.googlesource.com/'))

    def test_lock_rejects_unpinned_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'lock.json'
            for name in ('depot_tools','v8','angle'):
                lock=copy.deepcopy(self.lock);lock[name]['commit']='main'
                p.write_text(json.dumps(lock))
                with self.assertRaises(ValueError):deps.load_lock(p)

    def test_lock_rejects_changed_upstream(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock=copy.deepcopy(self.lock);lock['angle']['url']='https://example.com/fake'
            p=Path(tmp)/'lock.json';p.write_text(json.dumps(lock))
            with self.assertRaises(ValueError):deps.load_lock(p)

    def test_requested_v8_abi_and_sandbox(self):
        args=self.lock['v8']['gn_args']
        self.assertTrue(args['v8_enable_sandbox'])
        self.assertTrue(args['v8_enable_pointer_compression'])
        self.assertFalse(args['v8_use_external_startup_data'])
        self.assertFalse(args['v8_enable_i18n_support'])
        self.assertEqual(args['target_cpu'],'x64')

    def test_d3d11_only_angle_recipe(self):
        args=self.lock['angle']['gn_args']
        self.assertTrue(args['angle_enable_d3d11'])
        for name in ('gl','vulkan','metal','null','wgpu'):
            self.assertFalse(args['angle_enable_'+name])
        self.assertNotIn('angle_enable_d3d9',args)
        self.assertFalse(args['is_component_build'])

    def test_gn_booleans_and_strings_are_encoded(self):
        self.assertEqual(deps.gn_text({'z':'x64','a':True,'b':False}),
                         'a = true\nb = false\nz = "x64"\n')

    def test_gn_rejects_unrecognized_value_and_key(self):
        for args in ({'oops\nkey':True},{'list':[]}):
            with self.assertRaises(ValueError):deps.gn_text(args)

    def test_sdk_receipt_verifies_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            self.assertEqual(deps.verify_sdk(root,'v8',self.lock)['component'],'v8')

    def test_modified_archive_cannot_reuse_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            (root/'lib/v8_monolith.lib').write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):deps.verify_sdk(root,'v8',self.lock)

    def test_missing_required_sdk_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            (root/'include/v8-gn.h').unlink()
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',self.lock)

    def test_added_sdk_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            (root/'extra.dll').write_bytes(b'not inventoried')
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',self.lock)

    def test_other_component_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root,'angle')
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',self.lock)

    def test_other_abi_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            changed=copy.deepcopy(self.lock);changed['v8']['gn_args']['v8_enable_sandbox']=False
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',changed)

    def test_other_crt_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            changed=copy.deepcopy(self.lock);changed['crt']='MultiThreadedDLL'
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',changed)

    def test_receipt_must_include_all_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.make_sdk(root)
            p=root/deps.RECEIPT;value=json.loads(p.read_text())
            del value['sha256']['include/v8-gn.h'];p.write_text(json.dumps(value))
            with self.assertRaises(ValueError):deps.verify_sdk(root,'v8',self.lock)

    def test_dependency_stage_cannot_omit_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):deps.record_sdk(Path(tmp),'v8',self.lock)

    def test_crt_release_static_required(self):
        deps.validate_crt_directives('/DEFAULTLIB:"LIBCMT" /DEFAULTLIB:"OLDNAMES"')
        deps.validate_crt_directives('/DEFAULTLIB:libcmt.lib /NODEFAULTLIB:MSVCRT')
        for text in ('','/DEFAULTLIB:MSVCRT','/DEFAULTLIB:LIBCMTD',
                     '/DEFAULTLIB:LIBCMT /DEFAULTLIB:MSVCRT',
                     '/DEFAULTLIB:LIBCMT /DEFAULTLIB:"MSVCPRT"'):
            with self.assertRaises(ValueError):deps.validate_crt_directives(text)

    def test_build_command_preserves_spaces_as_one_argument(self):
        sdk=Path('SDK path 日本語');build=Path('Build space')
        command=build_command(sdk,build)
        self.assertIn('-DZERO_V8_ROOT='+str(sdk/'v8'),command)
        self.assertIn('-DZERO_ANGLE_DIR='+str(sdk/'angle/bin'),command)
        self.assertEqual(command[command.index('-B')+1],str(build))
        self.assertIn('-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',command)
        self.assertIn('-DCMAKE_BUILD_TYPE=Release',command)

    def test_minimal_build_does_not_stage_angle(self):
        command=build_command(Path('sdk'),Path('build'),False)
        self.assertIn('-DZERO_BUILD_GRAPHICS=OFF',command)
        self.assertFalse(any('ZERO_ANGLE_DIR' in x for x in command))

    def test_backend_is_explicit_not_silent_fallback(self):
        self.assertEqual(backend_args(None),[])
        self.assertEqual(backend_args('d3d11'),['--angle-backend','d3d11'])
        self.assertEqual(backend_args('warp'),['--angle-backend','warp'])
        with self.assertRaises(ValueError):backend_args('automatic')

    def test_default_binary_windows_and_linux(self):
        with patch('host_paths.sys.platform','win32'):
            self.assertEqual(default_host().name,'zero.exe')
        with patch('host_paths.sys.platform','linux'):
            self.assertEqual(default_host().name,'zero')

    def test_module_audit_requires_evidence(self):
        self.assertFalse(evaluate([],False)['passed'])
        self.assertFalse(evaluate([r'C:\Windows\System32\kernel32.dll'],True)['passed'])
        self.assertTrue(evaluate([r'C:\Windows\System32\kernel32.dll'],False)['passed'])

    def test_module_audit_requires_both_angle_dlls(self):
        paths=[r'C:\KZ\libEGL.dll',r'C:\KZ\libGLESv2.dll']
        self.assertTrue(evaluate(paths,True)['passed'])
        self.assertFalse(evaluate(paths[:1],True)['passed'])
        self.assertFalse(evaluate(paths,False)['passed'])

    def test_module_audit_detects_browser_or_node_images(self):
        for name in ('node.dll','libnode.dll','libcef.dll','chrome_elf.dll','electron.dll'):
            self.assertFalse(evaluate(['C:/KZ/'+name],False)['passed'])

    def test_nonwindows_is_not_runtime_validation(self):
        with patch('windows_deps.sys.platform','linux'):
            with self.assertRaises(ValueError):deps.require_windows()
            self.assertFalse(deps.doctor()['ready'])
        with patch('audit_windows.sys.platform','linux'):
            with self.assertRaises(OSError):module_paths(1)

    def test_angle_pixel_report_accepted_only_with_counters(self):
        for backend in ('angle-d3d11-pbuffer','angle-warp-pbuffer'):
            r=dict(status='completed',exit_code=0,graphics=dict(contexts=1,draw_calls=1,shader_compiles=2,pixel_reads=1,backend=backend),
                   logs=[{'text':'FRAME_RGBA8 1 1'},{'text':'ROW 0 ff0000ff'}])
            self.assertEqual(frame_pixels(r),(1,1,b'\xff\0\0'))
            r['graphics']['pixel_reads']=0
            with self.assertRaises(ValueError):frame_pixels(r)

    def test_fake_backend_pixel_report_rejected(self):
        r=dict(status='completed',exit_code=0,graphics=dict(contexts=1,draw_calls=1,shader_compiles=2,pixel_reads=1,backend='fake'),
               logs=[{'text':'FRAME_RGBA8 1 1'},{'text':'ROW 0 ff0000ff'}])
        with self.assertRaises(ValueError):frame_pixels(r)

    def test_batch_launcher_shell_metacharacters_rejected(self):
        with patch('windows_deps.shutil.which',return_value='C:/depot tools/gn.bat'):
            for bad in ('%PATH%','echo!value','one&two','a\nb','a|b'):
                with self.assertRaises(ValueError):deps.checked_tool('gn',[bad],Path('.'),{'PATH':'unused'})

    def test_windows_window_fixture_no_unsupported_uniform_api(self):
        # Shader parsing/pixels below are tested separately through native GL on Linux.
        source=(ROOT/'fixtures/windows-window.js').read_text(encoding='utf-8')
        self.assertNotIn('uniform1f',source)
        self.assertIn("event.type==='rawmousemove'",source)



class LauncherConstructionTests(unittest.TestCase):
    def test_batch_command_is_raw_cmd_line_not_double_crt_escaped(self):
        with patch('windows_deps.shutil.which',return_value='C:/depot tools/gclient.bat'), \
             patch('windows_deps.checked',return_value='') as execute:
            deps.checked_tool('gclient',['sync'],Path('.'),{'PATH':'unused'})
            command=execute.call_args.args[0]
            self.assertIsInstance(command,str)
            self.assertIn(' /d /v:off /s /c ""C:/depot tools/gclient.bat" sync"',command)
            self.assertNotIn('\\"',command)

    def test_native_tool_preserves_argument_list(self):
        with patch('windows_deps.shutil.which',return_value='C:/tools/gn.exe'), \
             patch('windows_deps.checked',return_value='') as execute:
            deps.checked_tool('gn',['gen','space path'],Path('.'),{'PATH':'unused'})
            self.assertEqual(execute.call_args.args[0],['C:/tools/gn.exe','gen','space path'])

if __name__=='__main__':unittest.main()
