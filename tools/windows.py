#!/usr/bin/env python3
"""Windows x64 developer entry point: doctor, deps, build, test, demo, package.

Run in x64 Developer PowerShell for VS 2022. No installation/admin policy changes.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from windows_deps import doctor, digest, load_lock, verify_sdk, require_windows
ROOT=Path(__file__).resolve().parents[1]


def build_command(sdk: Path, build: Path, graphics: bool=True) -> list[str]:
    command=['cmake','-S',str(ROOT),'-B',str(build),'-G','Ninja',
             '-DCMAKE_BUILD_TYPE=Release','-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',
             '-DZERO_BUILD_V8_HOST=ON','-DZERO_V8_ROOT='+str(sdk/'v8'),
             '-DZERO_BUILD_GRAPHICS='+('ON' if graphics else 'OFF')]
    if graphics:command+=['-DZERO_ANGLE_DIR='+str(sdk/'angle/bin')]
    return command


def run(command: list[str], logs: Path | None=None) -> None:
    print('+ '+subprocess.list2cmdline(command),flush=True)
    # Preserve literal path arguments; no shell=True for developer or host tools.
    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    if logs is None:
        subprocess.run(command,cwd=ROOT,env=env,check=True)
    else:
        logs.parent.mkdir(parents=True,exist_ok=True)
        with logs.open('w',encoding='utf-8') as output:
            child=subprocess.Popen(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            try:
                for line in child.stdout:
                    print(line,end='',flush=True);output.write(line);output.flush()
                if child.wait():raise subprocess.CalledProcessError(child.returncode,command)
            finally:
                if child.poll() is None:child.kill();child.wait()


def package(build: Path, sdk: Path, dest: Path) -> None:
    lock=load_lock()
    for name in ('v8','angle'):verify_sdk(sdk/name,name,lock)
    expected=[build/'zero.exe',build/'libEGL.dll',build/'libGLESv2.dll']
    for path in expected:
        if not path.is_file():raise ValueError('Missing build output: '+str(path))
    for name in ('libEGL.dll','libGLESv2.dll'):
        if digest(build/name)!=digest(sdk/'angle/bin'/name):
            raise ValueError('Built DLL does not match verified SDK: '+name)
    if dest.exists():raise ValueError('Output already exists; choose another package filename')
    files={str(p.name):p for p in expected}
    if (build/'d3dcompiler_47.dll').is_file():
        compiler=sdk/'angle/bin/d3dcompiler_47.dll'
        if not compiler.is_file() or digest(compiler)!=digest(build/'d3dcompiler_47.dll'):
            raise ValueError('Unverified app-local d3dcompiler_47.dll')
        files['d3dcompiler_47.dll']=compiler
    for name in ('v8','angle'):
        for p in (sdk/name).rglob('*'):
            if p.is_file() and ('licenses' in p.relative_to(sdk/name).parts or p.name in ('zero-sdk-receipt.json','REDISTRIBUTION-NOTICE.txt')):
                files['sdk-notices/'+name+'/'+p.relative_to(sdk/name).as_posix()]=p
    for doc in ('docs/WINDOWS.md','LOCAL_AGENT_HANDOFF.md','fixtures/windows-window.js'):
        files[doc]=ROOT/doc
    manifest=dict(schema=1,created_at=datetime.now(timezone.utc).isoformat(),
                  target='windows-x64',scope='PRIVATE DEVELOPMENT PACKAGE, NOT A PLAYABLE KRUNKER CLIENT',
                  windows_test_status='Consult separate local-agent test reports; packaging is not validation',
                  files={name:digest(path) for name,path in files.items()})
    dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,path in files.items():archive.write(path,name)
        archive.writestr('package-manifest.json',json.dumps(manifest,indent=2)+'\n')
    print('Private development package: '+str(dest))


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['doctor','deps','build','test','demo','package'])
    p.add_argument('--sdk',type=Path,default=ROOT/'deps/windows-x64')
    p.add_argument('--work',type=Path,default=Path('C:/kz-deps'))
    p.add_argument('--build-dir',type=Path,default=ROOT/'build/windows')
    p.add_argument('--reports',type=Path,default=ROOT/'reports/windows')
    p.add_argument('--angle-backend',choices=['d3d11','warp'],default='d3d11')
    p.add_argument('--interactive',action='store_true')
    p.add_argument('--core-only',action='store_true',help='Build no graphics; use a separate build directory')
    p.add_argument('--out',type=Path,default=ROOT/'dist/krunker-zero-windows-dev.zip')
    args=p.parse_args()
    try:
        if args.action=='doctor':
            result=doctor();print(json.dumps(result,indent=2));return 0 if result['ready'] else 1
        require_windows()
        sdk=args.sdk.resolve();build=args.build_dir.resolve();reports=args.reports.resolve();host=build/'zero.exe'
        py=sys.executable
        if args.action=='deps':
            run([py,str(ROOT/'tools/windows_deps.py'),'--work',str(args.work),'--out',str(sdk)],reports/'dependency-build.log')
        elif args.action=='build':
            if not doctor()['ready']:raise ValueError('Run doctor first in the x64 Visual Studio developer environment')
            lock=load_lock()
            for name in ('v8',) if args.core_only else ('v8','angle'):verify_sdk(sdk/name,name,lock)
            # Refuse accidental compiler/generator switching in an existing build tree.
            run(build_command(sdk,build,not args.core_only),reports/'cmake-configure.log')
            run(['cmake','--build',str(build),'--parallel','4'],reports/'build.log')
        elif args.action=='test':
            if args.core_only:raise ValueError('For a minimal build run tools/test.py --host <minimal zero.exe> directly; full Windows acceptance needs graphics')
            run(['ctest','--test-dir',str(build),'-C','Release','--output-on-failure'],reports/'native-tests.log')
            run([py,'tools/test.py','--host',str(host),'--report',str(reports/'standalone-tests.json')],reports/'standalone-tests.log')
            backend=['--angle-backend',args.angle_backend]
            run([py,'tools/test_graphics.py','--host',str(host),*backend,'--report',str(reports/'graphics-tests.json')],reports/'graphics-tests.log')
            run([py,'tools/render_probe.py','--host',str(host),*backend,'--out',str(reports/'native-triangle.png'),
                 '--report',str(reports/'render-probe.json')],reports/'render.log')
            run([py,'tools/test_windows.py','--host',str(host),*backend,*(['--interactive'] if args.interactive else []),
                 '--report',str(reports/'platform-tests.json')],reports/'platform-tests.log')
            for graphics in (False,True):
                name='graphics' if graphics else 'core'
                run([py,'tools/audit_windows.py','--host',str(host),*backend,*(['--graphics'] if graphics else []),
                     '--report',str(reports/(name+'-audit.json'))],reports/(name+'-audit.log'))
        elif args.action=='demo':
            run([str(host),'--profile','graphics','--window','--angle-backend',args.angle_backend,
                 '--timeout-ms','30000','--max-tasks','10000',str(ROOT/'fixtures/windows-window.js')],reports/'window-demo.log')
        elif args.action=='package':package(build,sdk,args.out.resolve())
        return 0
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        print('Windows workflow failed: '+str(exc),file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
