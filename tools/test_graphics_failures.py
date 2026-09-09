#!/usr/bin/env python3
"""Fault-inject missing EGL symbols and failed EGL initialization.

The deliberately broken shared libraries are TEST FIXTURES, never rendering
backends. Each is isolated to the child process via LD_LIBRARY_PATH. Successful
rendering is tested separately using the real driver by test_graphics.py.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[1]
MISSING='extern "C" void not_an_egl_library() {}\n'
INIT_FAILED=r'''
#include <cstring>
extern "C" {
void dummy() {}
void* display(unsigned,void*,const int*) { return reinterpret_cast<void*>(1); }
void* eglGetProcAddress(const char* name) {
  return std::strcmp(name,"eglGetPlatformDisplayEXT")==0 ? reinterpret_cast<void*>(&display) : reinterpret_cast<void*>(&dummy);
}
unsigned eglInitialize(void*,int*,int*) { return 1; }
unsigned eglBindAPI(unsigned) { return 0; }
unsigned eglChooseConfig(void*,const int*,void**,int,int*) { return 0; }
unsigned eglGetConfigAttrib(void*,void*,int,int*) { return 0; }
void* eglCreatePbufferSurface(void*,void*,const int*) { return nullptr; }
void* eglCreateContext(void*,void*,void*,const int*) { return nullptr; }
unsigned eglMakeCurrent(void*,void*,void*,void*) { return 1; }
unsigned eglDestroySurface(void*,void*) { return 1; }
unsigned eglDestroyContext(void*,void*) { return 1; }
unsigned eglTerminate(void*) { return 1; }
}
'''
SCRIPT='''let messages=[];for(let i=0;i<2;i++){
 try{new OffscreenCanvas(1,1).getContext('webgl');throw Error('unexpected context');}
 catch(e){messages.push(e.message);}}
if(messages.length!==2||messages[0]!==messages[1]||messages[0]==='unexpected context')throw Error('inconsistent failure');
console.log('EXPECTED_FAILURE_TWICE');
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',type=Path,default=ROOT/'build/standalone/zero')
    p.add_argument('--report',type=Path,default=ROOT/'reports/graphics-failure-tests.json')
    args=p.parse_args();host=args.host.resolve(strict=True);results=[]
    for name,source,expected in [('missing_symbol',MISSING,'eglGetProcAddress'),('initialization_failed',INIT_FAILED,'OpenGL ES API unavailable')]:
        r={};passed=False
        with tempfile.TemporaryDirectory(prefix='zero-egl-failure-') as tmp:
            root=Path(tmp);cpp=root/'fault.cc';cpp.write_text(source);js=root/'fixture.js';js.write_text(SCRIPT)
            try:
                subprocess.run([os.environ.get('CXX','c++'),'-shared','-fPIC',str(cpp),'-o',str(root/'libEGL.so.1')],check=True,capture_output=True,text=True,timeout=15)
                cp=subprocess.run([str(host),'--profile','graphics',str(js)],env=dict(os.environ,LD_LIBRARY_PATH=str(root)),capture_output=True,text=True,timeout=10)
                r=json.loads(cp.stdout)
                passed=(cp.returncode==0 and r.get('status')=='completed' and
                        [x['text'] for x in r.get('logs',[])]==['EXPECTED_FAILURE_TWICE'] and
                        r.get('graphics',{}).get('contexts')==0 and expected in r['graphics']['last_error'])
            except (OSError,ValueError,subprocess.SubprocessError) as exc:r=dict(error=str(exc))
        results.append(dict(name=name,passed=passed,fault_library_source_sha256=hashlib.sha256(source.encode()).hexdigest(),report=r))
        print(('PASS' if passed else 'FAIL')+': '+name)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(dict(schema=1,scope='Deliberately broken EGL test libraries; NOT evidence of rendering',passed=sum(r['passed'] for r in results),total=len(results),results=results),indent=2)+'\n')
    return 0 if all(r['passed'] for r in results) else 1

if __name__=='__main__':raise SystemExit(main())
