#!/usr/bin/env python3
"""Native Windows acceptance tests, never credited as passed on Linux/WSL.

Use --interactive on a logged-in desktop for actual HWND/presentation checks.
Keyboard/mouse behavior requires manual physical input; it is not fabricated.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from host_paths import default_host, backend_args
from windows_deps import require_windows
ROOT=Path(__file__).resolve().parents[1]


def execute(host: Path, script: Path, options: list[str], **kwargs) -> dict:
    cp=subprocess.run([str(host),*options,'--timeout-ms','10000','--',str(script)],
                      capture_output=True,text=True,encoding='utf-8',timeout=15,**kwargs)
    try:r=json.loads(cp.stdout)
    except ValueError:r={'status':'invalid_report','stdout':cp.stdout[:4096],'stderr':cp.stderr[:4096]}
    r['process_exit']=cp.returncode
    return r


def successful(r: dict) -> bool:
    return r.get('status')=='completed' and r.get('exit_code')==r.get('process_exit')==0


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=default_host())
    p.add_argument('--angle-backend',choices=['d3d11','warp'],default='d3d11')
    p.add_argument('--interactive',action='store_true')
    p.add_argument('--report',type=Path,default=ROOT/'reports/windows/platform-tests.json')
    args=p.parse_args();results=[];result={'schema':1,'status':'not_run','passed':0,'total':0,'results':results}
    try:
        require_windows();host=args.host.resolve(strict=True)
        engine=json.loads(subprocess.check_output([str(host),'--engine-info'],text=True,encoding='utf-8',timeout=5))
        def case(name,op,predicate):
            try:
                report=op();passed=bool(predicate(report))
            except (OSError,ValueError,subprocess.SubprocessError) as e:
                report={'error':str(e)};passed=False
            results.append(dict(name=name,passed=passed,report=report))
            print(('PASS: ' if passed else 'FAIL: ')+name,flush=True)
        case('native_windows_engine_identity',lambda:engine,
             lambda r:r.get('platform')=='windows-x64' and r.get('host')=='standalone' and r.get('graphics_compiled') is True)
        with tempfile.TemporaryDirectory(prefix='zero-win-tests-') as tmp:
            temp=Path(tmp); script=temp/'probe.js'
            script.write_text('console.log("PASS");',encoding='utf-8')
            # Paths with spaces, BMP and supplementary Unicode in executable AND script.
            unicode_dir=temp/'Unicode path 日本語 🚀';unicode_dir.mkdir()
            copied=unicode_dir/'zero.exe';shutil.copy2(host,copied)
            unicode_script=unicode_dir/'入力 🚀.js'
            unicode_script.write_text('console.log("日本語 🚀");',encoding='utf-8')
            case('unicode_executable_input_and_json',lambda:execute(copied,unicode_script,['--profile','core']),
                 lambda r:successful(r) and [v['text'] for v in r['logs']]==['日本語 🚀'])
            case('core_without_angle_dlls',lambda:execute(copied,script,['--profile','core']),successful)
            for name,options in [('window_core_rejected',['--profile','core','--window']),
                                 ('window_virtual_time_rejected',['--profile','graphics','--window','--virtual-time']),
                                 ('invalid_backend_rejected',['--profile','graphics','--angle-backend','automatic']),
                                 ('angle_in_core_rejected',['--profile','core','--angle-backend','warp']),
                                 ('invalid_swap_interval_rejected',['--profile','graphics','--swap-interval','2'])]:
                case(name,lambda options=options:execute(host,script,options),
                     lambda r:r.get('status')=='configuration_error' and r.get('process_exit')==64)
            failure=temp/'missing-angle.js';failure.write_text('''
let messages=[];for(let i=0;i<2;i++){try{new OffscreenCanvas(1,1).getContext('webgl');throw Error('unexpected context')}
catch(e){messages.push(e.message)}}
if(messages[0]!==messages[1]||messages[0]==='unexpected context')throw Error('inconsistent loading failure');
console.log('EXPECTED_FAILURE_TWICE');
''',encoding='utf-8')
            # The real DLL pair remains in host.parent, which is deliberately placed
            # on BOTH CWD/PATH while the executable's own directory contains none.
            case('no_cwd_or_path_dll_fallback',lambda:execute(copied,failure,['--profile','graphics',*backend_args(args.angle_backend)],
                  cwd=host.parent,env=dict(os.environ,PATH=str(host.parent)+os.pathsep+os.environ.get('PATH',''))),
                 lambda r:successful(r) and r.get('graphics',{}).get('contexts')==0
                 and 'Cannot load' in r['graphics']['last_error']
                 and [v['text'] for v in r['logs']]==['EXPECTED_FAILURE_TWICE'])
            for name in ('libEGL.dll','libGLESv2.dll','d3dcompiler_47.dll'):
                if (host.parent/name).is_file():shutil.copy2(host.parent/name,unicode_dir/name)
            render=temp/'color.js';render.write_text('''
if(typeof zeroWindow!=='undefined')throw Error('window API leaked');
const gl=new OffscreenCanvas(8,8).getContext('webgl');
gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);const p=new Uint8Array(4);
gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);
if(Array.from(p).join()!=='255,0,0,255')throw Error('wrong native pixels');console.log('PASS');
''',encoding='utf-8')
            case('app_local_angle_from_unicode_path',lambda:execute(copied,render,['--profile','graphics',*backend_args(args.angle_backend)]),
                 lambda r:successful(r) and r.get('graphics',{}).get('backend')=='angle-'+args.angle_backend+'-pbuffer'
                 and r['graphics']['pixel_reads']==1)
            if args.interactive:
                window=temp/'present.js';window.write_text('''
const canvas=zeroWindow.create(128,128),gl=canvas.getContext('webgl');
requestAnimationFrame(()=>{gl.clearColor(0,1,0,1);gl.clear(gl.COLOR_BUFFER_BIT);
if(!zeroWindow.present(canvas))throw Error('window did not present');console.log('PRESENTED');});
''',encoding='utf-8')
                case('actual_native_window_swap',lambda:execute(host,window,['--profile','graphics','--window',*backend_args(args.angle_backend)]),
                     lambda r:successful(r) and r.get('graphics',{}).get('window_created') is True
                     and r['graphics']['presented_frames']==1)
                events=temp/'events.js';events.write_text('''
zeroWindow.create(64,64);
for(const key of ['type','x','y','code','repeat'])Object.defineProperty(Object.prototype,key,{set(){throw Error('prototype setter called')},configurable:true});
try{const events=zeroWindow.pollEvents();if(!Array.isArray(events))throw Error('not events');}
finally{for(const key of ['type','x','y','code','repeat'])delete Object.prototype[key];}
console.log('SAFE_EVENTS');
''',encoding='utf-8')
                case('native_events_ignore_prototype_setters',lambda:execute(host,events,['--profile','graphics','--window',*backend_args(args.angle_backend)]),successful)
                close=temp/'close.js';close.write_text('''
zeroWindow.create(64,64);
setTimeout(()=>zeroWindow.close(),0);
setTimeout(()=>{throw Error('callback ran after close')},0);
''',encoding='utf-8')
                case('close_cancels_remaining_callbacks',lambda:execute(host,close,['--profile','graphics','--window',*backend_args(args.angle_backend)]),
                     lambda r:r.get('status')=='window_closed' and r.get('process_exit')==0 and r.get('callbacks')==1)
        result.update(status='tested',engine=engine,executable_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),
                      passed=sum(v['passed'] for v in results),total=len(results),interactive_requested=args.interactive,
                      manual_input='not automated; physically test focus, Escape release, keyboard and raw mouse with the demo')
        return 0 if all(v['passed'] for v in results) else 1
    except (OSError,ValueError,subprocess.SubprocessError) as e:
        result['error']=str(e);print('Windows tests not passed: '+str(e),file=sys.stderr);return 1
    finally:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


if __name__=='__main__':raise SystemExit(main())
