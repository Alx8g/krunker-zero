#!/usr/bin/env python3
"""Observe loaded modules of our OWN Windows child, plus PE import dependencies.

One fixture-path dependency audit, not a sandbox/security/performance proof.
Does not inspect any other application, browser, game process or user's account.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from host_paths import default_host, backend_args
ROOT=Path(__file__).resolve().parents[1]


def module_paths(pid: int) -> list[str]:
    if sys.platform!='win32': raise OSError('Win32 Toolhelp is unavailable on this OS')
    class MODULEENTRY32W(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('th32ModuleID',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),
                  ('GlblcntUsage',wintypes.DWORD),('ProccntUsage',wintypes.DWORD),
                  ('modBaseAddr',ctypes.POINTER(wintypes.BYTE)),('modBaseSize',wintypes.DWORD),
                  ('hModule',wintypes.HMODULE),('szModule',wintypes.WCHAR*256),('szExePath',wintypes.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    api.Module32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MODULEENTRY32W)]
    api.Module32FirstW.restype=wintypes.BOOL
    api.Module32NextW.argtypes=api.Module32FirstW.argtypes;api.Module32NextW.restype=wintypes.BOOL
    api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle.restype=wintypes.BOOL
    snapshot=api.CreateToolhelp32Snapshot(0x8|0x10,pid)
    if snapshot==ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry=MODULEENTRY32W();entry.dwSize=ctypes.sizeof(entry);result=[]
        if not api.Module32FirstW(snapshot,ctypes.byref(entry)): raise ctypes.WinError(ctypes.get_last_error())
        while True:
            result.append(entry.szExePath)
            if not api.Module32NextW(snapshot,ctypes.byref(entry)):
                code=ctypes.get_last_error()
                if code!=18:raise ctypes.WinError(code) # ERROR_NO_MORE_FILES
                break
        return result
    finally: api.CloseHandle(snapshot)


def evaluate(paths: list[str], graphics: bool) -> dict:
    # ntpath semantics also when unit-testing this pure function on Linux.
    import ntpath
    names={ntpath.basename(p).lower() for p in paths}
    forbidden=[n for n in sorted(names) if re.match(r'^(?:libnode|node|libcef|cef|chromium|chrome(?:_elf)?|electron)(?:[.\-_]|$)',n)]
    angle={'libegl.dll','libglesv2.dll'}
    seen=angle.intersection(names)
    return dict(unexpected_browser_or_node_modules=forbidden,angle_modules=sorted(seen),
                passed=bool(paths) and not forbidden and (seen==angle if graphics else not seen))


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=default_host());p.add_argument('--graphics',action='store_true')
    p.add_argument('--angle-backend',choices=['d3d11','warp'],default='d3d11')
    p.add_argument('--report',type=Path,default=ROOT/'reports/windows/binary-audit.json')
    args=p.parse_args();child=None;result={'status':'not_run','passed':False,'platform':sys.platform}
    try:
        if sys.platform!='win32' or sys.maxsize<=2**32:raise ValueError('Run with 64-bit Python on native Windows')
        host=args.host.resolve(strict=True);dumpbin=shutil.which('dumpbin')
        if not dumpbin:raise ValueError('dumpbin not found; use x64 Visual Studio developer environment')
        imports=subprocess.check_output([dumpbin,'/dependents',str(host)],text=True,encoding='utf-8',errors='replace',timeout=15)
        imported=re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports,re.M|re.I)
        engine=json.loads(subprocess.check_output([str(host),'--engine-info'],text=True,encoding='utf-8',timeout=5))
        images=set();errors=[]
        source=('new OffscreenCanvas(8,8).getContext("webgl");\n' if args.graphics else '')+'setTimeout(()=>{},2500);\n'
        with tempfile.TemporaryDirectory(prefix='zero-audit-') as temp:
            path=Path(temp)/'probe.js';path.write_text(source,encoding='utf-8')
            command=[str(host),'--profile','graphics' if args.graphics else 'core','--timeout-ms','12000']
            if args.graphics:command+=backend_args(args.angle_backend)
            child=subprocess.Popen([*command,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
            deadline=time.monotonic()+15
            while child.poll() is None and time.monotonic()<deadline:
                try:images.update(module_paths(child.pid))
                except OSError as error:
                    if len(errors)<10:errors.append(str(error))
                time.sleep(.03)
            out,err=child.communicate(timeout=2)
            native=json.loads(out)
            if child.returncode or native.get('status')!='completed':raise ValueError('Native audit fixture failed: '+out[:2048]+err[:1024])
        result=dict(schema=1,status='tested',platform='windows-x64',bytes=host.stat().st_size,
                    sha256=hashlib.sha256(host.read_bytes()).hexdigest(),engine_info=engine,
                    direct_pe_imports=imported,observed_runtime_modules=sorted(images),snapshot_errors=errors,
                    native_report=native,scope='Own-child fixture observation, not a security/minimum-footprint/game proof',
                    **evaluate([*images,*imported],args.graphics))
        result['passed'] = result['passed'] and bool(images)
        result['runtime_modules_observed'] = bool(images)
        return 0 if result['passed'] else 1
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        result['error']=str(exc);print('Windows audit not passed: '+str(exc),file=sys.stderr);return 1
    finally:
        if child and child.poll() is None:child.kill();child.communicate(timeout=3)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':raise SystemExit(main())
