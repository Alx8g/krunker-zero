#!/usr/bin/env python3
"""Execute optional native EGL pixel/safety fixtures. No browser or Node is used."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PRELUDE = r'''
function assert(x,m='assertion failed'){if(!x)throw Error(m)}
function eq(a,b){assert(JSON.stringify(a)===JSON.stringify(b),JSON.stringify(a)+' != '+JSON.stringify(b))}
const canvas=new OffscreenCanvas(32,32),gl=canvas.getContext('webgl');assert(gl);
function pixel(x=16,y=16){const p=new Uint8Array(4);gl.readPixels(x,y,1,1,gl.RGBA,gl.UNSIGNED_BYTE,p);return Array.from(p)}
function compile(type,src){let s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);assert(gl.getShaderParameter(s,gl.COMPILE_STATUS),gl.getShaderInfoLog(s));return s}
function program(fragment='precision mediump float; uniform vec4 tint; void main(){gl_FragColor=tint;}'){
 const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,'attribute vec2 pos; void main(){gl_Position=vec4(pos,0.0,1.0);}'));
 gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fragment));gl.linkProgram(p);assert(gl.getProgramParameter(p,gl.LINK_STATUS),gl.getProgramInfoLog(p));return p;
}
function setup(){const p=program();gl.useProgram(p);const loc=gl.getUniformLocation(p,'tint');gl.uniform4f(loc,1,0,0,1);
 const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,0,1]),gl.STATIC_DRAW);
 const v=gl.getAttribLocation(p,'pos');gl.enableVertexAttribArray(v);gl.vertexAttribPointer(v,2,gl.FLOAT,false,0,0);return {p,b,v,loc};}
function error(e){eq(gl.getError(),e);eq(gl.getError(),0)}
'''
CASES = [
 ('zero_initialized_framebuffer', 'eq(pixel(),[0,0,0,0]);error(0);'),
 ('clear_pixels', 'gl.clearColor(.25,.5,.75,1);gl.clear(gl.COLOR_BUFFER_BIT);let p=pixel();assert(Math.abs(p[0]-64)<=1&&Math.abs(p[1]-128)<=1&&Math.abs(p[2]-191)<=1&&p[3]===255);error(0);'),
 ('native_triangle_pixels', 'setup();gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[255,0,0,255]);eq(pixel(0,31),[0,0,0,0]);error(0);'),
 ('indexed_triangle_pixels', 'setup();let i=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,i);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint16Array([0,1,2]),gl.STATIC_DRAW);gl.drawElements(gl.TRIANGLES,3,gl.UNSIGNED_SHORT,0);eq(pixel(),[255,0,0,255]);error(0);'),
 ('view_offset_upload', 'const s=setup(),data=new Float32Array([77,77,-1,-1,1,-1,0,1,77]);gl.bufferData(gl.ARRAY_BUFFER,data.subarray(2,8),gl.STATIC_DRAW);gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[255,0,0,255]);error(0);'),
 ('view_offset_readback', 'gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);const a=new Uint8Array(12).fill(99);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,a.subarray(4,8));eq(Array.from(a),[99,99,99,99,255,0,0,255,99,99,99,99]);error(0);'),
 ('upload_copy_not_borrowed', 'setup();let v=new Float32Array([-1,-1,1,-1,0,1]);gl.bufferData(gl.ARRAY_BUFFER,v,gl.STATIC_DRAW);v.fill(0);gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[255,0,0,255]);error(0);'),
 ('subdata_changes_real_vertices', 'setup();gl.bufferSubData(gl.ARRAY_BUFFER,0,new Float32Array([0,0,0,0,0,0]));gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[0,0,0,0]);error(0);'),
 ('size_only_buffer_zeroed', 'setup();gl.bufferData(gl.ARRAY_BUFFER,24,gl.STATIC_DRAW);gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[0,0,0,0]);error(0);'),
 ('drawarrays_bounds_rejected', 'setup();gl.drawArrays(gl.TRIANGLES,0,4);error(gl.INVALID_OPERATION);eq(pixel(),[0,0,0,0]);'),
 ('index_buffer_bounds_rejected', 'setup();let b=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint8Array([0,1]),gl.STATIC_DRAW);gl.drawElements(gl.TRIANGLES,3,gl.UNSIGNED_BYTE,0);error(gl.INVALID_OPERATION);'),
 ('index_value_bounds_rejected', 'setup();let b=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint8Array([0,1,99]),gl.STATIC_DRAW);gl.drawElements(gl.TRIANGLES,3,gl.UNSIGNED_BYTE,0);error(gl.INVALID_OPERATION);'),
 ('index_subdata_revalidated', 'setup();let b=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,new Uint8Array([0,1,2]),gl.STATIC_DRAW);gl.bufferSubData(gl.ELEMENT_ARRAY_BUFFER,2,new Uint8Array([255]));gl.drawElements(gl.TRIANGLES,3,gl.UNSIGNED_BYTE,0);error(gl.INVALID_OPERATION);'),
 ('index_alignment_rejected', 'setup();let b=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,8,gl.STATIC_DRAW);gl.drawElements(gl.TRIANGLES,3,gl.UNSIGNED_SHORT,1);error(gl.INVALID_OPERATION);'),
 ('vertex_alignment_rejected', 'const s=setup();gl.vertexAttribPointer(s.v,2,gl.FLOAT,false,0,1);error(gl.INVALID_OPERATION);'),
 ('vertex_stride_rejected', 'const s=setup();gl.vertexAttribPointer(s.v,2,gl.FLOAT,false,256,0);error(gl.INVALID_VALUE);'),
 ('vertex_stride_bounds_rejected', 'const s=setup();gl.vertexAttribPointer(s.v,2,gl.FLOAT,false,16,0);gl.drawArrays(gl.TRIANGLES,0,3);error(gl.INVALID_OPERATION);'),
 ('deleted_buffer_no_dangling_read', 'const s=setup();gl.deleteBuffer(s.b);gl.drawArrays(gl.TRIANGLES,0,3);error(gl.INVALID_OPERATION);'),
 ('delete_idempotent', 'let b=gl.createBuffer();gl.deleteBuffer(b);gl.deleteBuffer(b);gl.deleteBuffer(null);error(0);'),
 ('deleted_handle_not_recycled', 'let b=gl.createBuffer();gl.deleteBuffer(b);let b2=gl.createBuffer();assert(b!==b2);gl.bindBuffer(gl.ARRAY_BUFFER,b);error(gl.INVALID_OPERATION);'),
 ('cross_context_handle_rejected', "const other=new OffscreenCanvas(1,1).getContext('webgl');gl.bindBuffer(gl.ARRAY_BUFFER,other.createBuffer());error(gl.INVALID_OPERATION);"),
 ('forged_handle_rejected', 'let caught=false;try{gl.bindBuffer(gl.ARRAY_BUFFER,Object.create(WebGLBuffer.prototype))}catch(e){caught=e instanceof TypeError}assert(caught);error(0);'),
 ('wrong_kind_handle_rejected', 'let caught=false;try{gl.bindBuffer(gl.ARRAY_BUFFER,gl.createShader(gl.VERTEX_SHADER))}catch(e){caught=e instanceof TypeError}assert(caught);error(0);'),
 ('buffer_target_change_rejected', 'const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,b);error(gl.INVALID_OPERATION);'),
 ('subdata_overrun_rejected', 'setup();gl.bufferSubData(gl.ARRAY_BUFFER,23,new Uint8Array(2));error(gl.INVALID_VALUE);'),
 ('allocation_cap_checked', 'setup();gl.bufferData(gl.ARRAY_BUFFER,67108865,gl.STATIC_DRAW);error(gl.OUT_OF_MEMORY);'),
 ('negative_buffer_size_rejected', 'setup();gl.bufferData(gl.ARRAY_BUFFER,-1,gl.STATIC_DRAW);error(gl.INVALID_VALUE);'),
 ('failed_shader_not_success', "const s=gl.createShader(gl.FRAGMENT_SHADER);gl.shaderSource(s,'this is not a shader');gl.compileShader(s);assert(!gl.getShaderParameter(s,gl.COMPILE_STATUS));assert(gl.getShaderInfoLog(s).length>0);error(0);"),
 ('failed_link_not_success', 'const p=gl.createProgram();gl.linkProgram(p);assert(!gl.getProgramParameter(p,gl.LINK_STATUS));gl.useProgram(p);error(gl.INVALID_OPERATION);'),
 ('uniform_relink_invalidates_location', 'const s=setup();gl.linkProgram(s.p);gl.uniform4f(s.loc,0,1,0,1);error(gl.INVALID_OPERATION);'),
 ('uniform_wrong_program_rejected', 'const s=setup();gl.useProgram(program());gl.uniform4f(s.loc,0,1,0,1);error(gl.INVALID_OPERATION);'),
 ('uniform_updates_pixels', 'const s=setup();gl.uniform4f(s.loc,0,1,0,1);gl.drawArrays(gl.TRIANGLES,0,3);eq(pixel(),[0,255,0,255]);error(0);'),
 ('short_read_destination_unchanged', 'const a=new Uint8Array(3).fill(77);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,a);error(gl.INVALID_OPERATION);eq(Array.from(a),[77,77,77]);'),
 ('read_destination_type_checked', 'const a=new Float32Array(4).fill(77);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,a);error(gl.INVALID_OPERATION);eq(Array.from(a),[77,77,77,77]);'),
 ('read_outside_zero_filled', 'gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);const a=new Uint8Array(16).fill(77);gl.readPixels(-1,-1,2,2,gl.RGBA,gl.UNSIGNED_BYTE,a);eq(Array.from(a),[0,0,0,0,0,0,0,0,0,0,0,0,255,0,0,255]);error(0);'),
 ('huge_read_no_overflow', 'const a=new Uint8Array(4).fill(77);gl.readPixels(0,0,2147483647,2147483647,gl.RGBA,gl.UNSIGNED_BYTE,a);error(gl.INVALID_OPERATION);eq(Array.from(a),[77,77,77,77]);'),
 ('resize_zero_initializes', 'gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);canvas.width=17;eq(pixel(0,0),[0,0,0,0]);eq(gl.drawingBufferWidth,17);gl.clear(gl.COLOR_BUFFER_BIT);eq(pixel(0,0),[255,0,0,255]);error(0);'),
 ('resize_with_write_masks_still_zeroes', 'gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);gl.colorMask(false,false,false,false);gl.depthMask(false);canvas.height=17;eq(pixel(0,0),[0,0,0,0]);gl.clear(gl.COLOR_BUFFER_BIT);eq(pixel(0,0),[0,0,0,0]);error(0);'),
 ('switching_contexts_preserves_pixels', "gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);const o=new OffscreenCanvas(32,32).getContext('webgl');o.clearColor(0,1,0,1);o.clear(o.COLOR_BUFFER_BIT);eq(pixel(),[255,0,0,255]);error(0);"),
 ('extension_and_context_detection', "eq(gl.getSupportedExtensions(),[]);eq(gl.getExtension('OES_element_index_uint'),null);eq(canvas.getContext('2d'),null);eq(canvas.getContext('webgl2'),null);assert(canvas.getContext('experimental-webgl')===gl);"),
 ('absent_browser_and_private_bridge', "eq([typeof document,typeof fetch,typeof WebSocket,typeof process,typeof __zeroGraphicsNative],['undefined','undefined','undefined','undefined','undefined']);"),
 ('integer_overflow_draw_rejected', 'setup();gl.drawArrays(gl.TRIANGLES,2147483647,2147483647);error(gl.INVALID_OPERATION);'),
 ('detached_upload_rejected', "const s=setup(),a=new Uint8Array(8);a.buffer.transfer();let caught=false;try{gl.bufferData(gl.ARRAY_BUFFER,a,gl.STATIC_DRAW)}catch(e){caught=true}assert(caught);"),
 ('deleted_program_query_rejected', 'const s=setup();gl.useProgram(null);gl.deleteProgram(s.p);gl.createProgram();eq(gl.getProgramParameter(s.p,gl.LINK_STATUS),null);error(gl.INVALID_VALUE);assert(gl.getProgramParameter(s.p,gl.DELETE_STATUS));'),
 ('nul_uniform_name_rejected', "const s=setup();eq(gl.getUniformLocation(s.p,'color\\0trailer'),null);error(gl.INVALID_VALUE);"),
 ('nul_attribute_name_rejected', "const s=setup();eq(gl.getAttribLocation(s.p,'position\\0trailer'),-1);error(gl.INVALID_VALUE);"),
 ('delete_releases_allocation_budget', 'for(let i=0;i<16;i++){let b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,8388608,gl.STATIC_DRAW);error(0);gl.deleteBuffer(b);}'),
 ('intrinsic_tampering_cannot_forge_native_state', "const old=[WeakMap.prototype.get,WeakMap.prototype.set,Object.create,Number];try{WeakMap.prototype.get=()=>({id:999});WeakMap.prototype.set=()=>{throw Error('tampered set')};Object.create=()=>{throw Error('tampered create')};globalThis.Number=()=>{throw Error('tampered Number')};const c=new OffscreenCanvas(1,1),o=c.getContext('webgl');const b=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,b);gl.bufferData(gl.ARRAY_BUFFER,16,gl.STATIC_DRAW);gl.clearColor(1,0,0,1);gl.clear(gl.COLOR_BUFFER_BIT);}finally{[WeakMap.prototype.get,WeakMap.prototype.set,Object.create,globalThis.Number]=old;}eq(pixel(),[255,0,0,255]);error(0);"),
 ('object_cap_bounded', 'for(let i=0;i<4096;i++)assert(gl.createBuffer());eq(gl.createBuffer(),null);error(gl.OUT_OF_MEMORY);'),
 ('context_cap_bounded', "for(let i=1;i<8;i++)assert(new OffscreenCanvas(1,1).getContext('webgl'));let caught=false;try{new OffscreenCanvas(1,1).getContext('webgl')}catch(e){caught=true}assert(caught);"),
]

def run(host: Path, report: Path) -> int:
    results=[]
    for name,body in CASES:
        raw=(PRELUDE+'\n'+body+'\nconsole.log("PASS");').encode()
        with tempfile.TemporaryDirectory(prefix='zero-graphics-') as tmp:
            path=Path(tmp)/'fixture.js';path.write_bytes(raw)
            try:
                cp=subprocess.run([str(host),'--profile','graphics','--timeout-ms','10000',str(path)],capture_output=True,text=True,timeout=15)
                r=json.loads(cp.stdout)
                passed=cp.returncode==0 and r.get('status')=='completed' and [x['text'] for x in r.get('logs',[])]==['PASS']
                if name == 'delete_releases_allocation_budget':
                    passed = passed and r.get('graphics',{}).get('cpu_shadow_capacity_bytes') == 0
            except (OSError,ValueError,subprocess.TimeoutExpired) as e:
                r={'error':str(e)};passed=False
        results.append(dict(name=name,passed=passed,fixture_sha256=hashlib.sha256(raw).hexdigest(),report=r))
        print(('PASS' if passed else 'FAIL')+': '+name,flush=True)
        if not passed: print(r,flush=True)
    outcome=dict(schema=1,executable_sha256=hashlib.sha256(host.read_bytes()).hexdigest(),environment='standalone V8 + native EGL, no browser or Node',
                 scope='independent graphics fixtures; NOT Krunker and NOT WebGL conformance certification',
                 passed=sum(x['passed'] for x in results),total=len(results),results=results)
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(outcome,indent=2)+'\n')
    print(f"{outcome['passed']}/{len(results)} native graphics cases passed")
    return 0 if outcome['passed']==len(results) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',type=Path,default=ROOT/'build/standalone/zero');p.add_argument('--report',type=Path,default=ROOT/'reports/graphics-tests.json')
    args=p.parse_args();raise SystemExit(run(args.host.resolve(strict=True),args.report))
