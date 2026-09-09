/* Experimental, fixture-driven WebGL-shaped subset. No DOM or browser fallback.
 * Only installed by the explicit graphics profile. Native code owns all real GL
 * resources; WeakMaps keep driver names/addresses out of guest-visible objects.
 */
((native) => {
  'use strict';
  delete globalThis.__zeroGraphicsNative;
  const canvasState = new WeakMap(), glState = new WeakMap(), resourceState = new WeakMap();
  // Cache the few intrinsics used across the native boundary before guest code
  // can replace prototypes. Hidden state must not go through a guest-supplied
  // WeakMap.get/set or Object.create implementation.
  const get = Function.prototype.call.bind(WeakMap.prototype.get);
  const set = Function.prototype.call.bind(WeakMap.prototype.set);
  const create = Object.create, numeric = Number;
  const finite = Number.isFinite, integer = Number.isInteger;
  const TypeErr = TypeError, RangeErr = RangeError;
  const enum32 = x => numeric(x) | 0;
  const real = x => { const n=numeric(x); if(!finite(n)) throw TypeErr('Expected a finite GLfloat'); return n; };
  const str = x => '' + x;
  const dimension = x => {
    const n=numeric(x);
    if(!integer(n)||n<1||n>2048) throw RangeErr('Experimental canvas dimensions must be 1..2048');
    return n;
  };
  function state(gl) {const s=get(glState,gl);if(!s)throw TypeErr('Illegal invocation');return s;}
  function error(s,e) {native('error',s.id,e);}
  const classes = {};
  for(const name of ['WebGLBuffer','WebGLShader','WebGLProgram','WebGLUniformLocation']) {
    const ctor = {[name]:class {constructor(){throw TypeErr('Illegal constructor');}}}[name];
    classes[name]=ctor;Object.defineProperty(globalThis,name,{value:ctor,configurable:true,writable:true});
  }
  function wrap(s,kind,id) {
    if(!id)return null;
    const o=create(classes[kind].prototype);
    set(resourceState,o,{context:s,kind,id});return o;
  }
  function handle(s,value,kind,nullable=false) {
    if(nullable&&(value===null||value===undefined))return 0;
    const r=get(resourceState,value);
    if(!r||r.kind!==kind)throw TypeErr('Expected '+kind);
    if(r.context!==s){error(s,0x0502);return -1;}
    return r.id;
  }
  class OffscreenCanvas {
    constructor(width,height) {set(canvasState,this,{width:dimension(width),height:dimension(height),gl:null});}
    get width(){const s=get(canvasState,this);if(!s)throw TypeErr('Illegal invocation');return s.width;}
    set width(value){const s=get(canvasState,this);if(!s)throw TypeErr('Illegal invocation');const w=dimension(value);
      if(s.gl)native('resize',state(s.gl).id,w,s.height);s.width=w;}
    get height(){const s=get(canvasState,this);if(!s)throw TypeErr('Illegal invocation');return s.height;}
    set height(value){const s=get(canvasState,this);if(!s)throw TypeErr('Illegal invocation');const h=dimension(value);
      if(s.gl)native('resize',state(s.gl).id,s.width,h);s.height=h;}
    getContext(type,options={}) {
      const c=get(canvasState,this);if(!c)throw TypeErr('Illegal invocation');type=str(type);
      if(type!=='webgl'&&type!=='experimental-webgl')return null;
      if(c.gl)return c.gl;
      if(options===null)options={};
      // Unsupported mandatory buffer formats fail rather than misreporting the
      // native surface as one we did not create. No silent software fallback.
      if(options.alpha===false||options.premultipliedAlpha===false||options.failIfMajorPerformanceCaveat===true)return null;
      const id=native('create',c.width,c.height);
      const gl=create(WebGLRenderingContext.prototype);
      set(glState,gl,{id,canvas:this,attributes:{alpha:true,depth:true,stencil:false,antialias:false,
        premultipliedAlpha:true,preserveDrawingBuffer:!!options.preserveDrawingBuffer,
        failIfMajorPerformanceCaveat:false,desynchronized:false,powerPreference:'default'}});
      c.gl=gl;return gl;
    }
  }
  class WebGLRenderingContext {
    constructor(){throw TypeErr('Illegal constructor');}
    get canvas(){return state(this).canvas;}
    get drawingBufferWidth(){return get(canvasState,state(this).canvas).width;}
    get drawingBufferHeight(){return get(canvasState,state(this).canvas).height;}
    getContextAttributes(){return {...state(this).attributes};}
    getSupportedExtensions(){state(this);return [];}
    getExtension(name){state(this);str(name);return null;}
    getError(){return native('getError',state(this).id);}
    getParameter(p){return native('getParameter',state(this).id,enum32(p));}
    viewport(x,y,w,h){native('viewport',state(this).id,enum32(x),enum32(y),enum32(w),enum32(h));}
    clearColor(r,g,b,a){native('clearColor',state(this).id,real(r),real(g),real(b),real(a));}
    clearDepth(d){native('clearDepth',state(this).id,real(d));}
    clear(mask){native('clear',state(this).id,enum32(mask));}
    finish(){native('finish',state(this).id);}
    flush(){native('flush',state(this).id);}
    enable(cap){native('enable',state(this).id,enum32(cap));}
    disable(cap){native('disable',state(this).id,enum32(cap));}
    depthFunc(fn){native('depthFunc',state(this).id,enum32(fn));}
    depthMask(flag){native('depthMask',state(this).id,!!flag);}
    colorMask(r,g,b,a){native('colorMask',state(this).id,!!r,!!g,!!b,!!a);}
    createShader(type){const s=state(this);return wrap(s,'WebGLShader',native('createShader',s.id,enum32(type)));}
    shaderSource(shader,source){const s=state(this),id=handle(s,shader,'WebGLShader');if(id>=0)native('shaderSource',s.id,id,str(source));}
    compileShader(shader){const s=state(this),id=handle(s,shader,'WebGLShader');if(id>=0)native('compileShader',s.id,id);}
    getShaderParameter(shader,p){const s=state(this),id=handle(s,shader,'WebGLShader');return id<0?null:native('getShaderParameter',s.id,id,enum32(p));}
    getShaderInfoLog(shader){const s=state(this),id=handle(s,shader,'WebGLShader');return id<0?null:native('getShaderInfoLog',s.id,id);}
    deleteShader(shader){const s=state(this),id=handle(s,shader,'WebGLShader',true);if(id>=0)native('deleteShader',s.id,id);}
    createProgram(){const s=state(this);return wrap(s,'WebGLProgram',native('createProgram',s.id));}
    attachShader(program,shader){const s=state(this),p=handle(s,program,'WebGLProgram'),h=handle(s,shader,'WebGLShader');if(p>=0&&h>=0)native('attachShader',s.id,p,h);}
    linkProgram(program){const s=state(this),id=handle(s,program,'WebGLProgram');if(id>=0)native('linkProgram',s.id,id);}
    getProgramParameter(program,p){const s=state(this),id=handle(s,program,'WebGLProgram');return id<0?null:native('getProgramParameter',s.id,id,enum32(p));}
    getProgramInfoLog(program){const s=state(this),id=handle(s,program,'WebGLProgram');return id<0?null:native('getProgramInfoLog',s.id,id);}
    useProgram(program){const s=state(this),id=handle(s,program,'WebGLProgram',true);if(id>=0)native('useProgram',s.id,id);}
    deleteProgram(program){const s=state(this),id=handle(s,program,'WebGLProgram',true);if(id>=0)native('deleteProgram',s.id,id);}
    getAttribLocation(program,name){const s=state(this),id=handle(s,program,'WebGLProgram');return id<0?-1:native('getAttribLocation',s.id,id,str(name));}
    getUniformLocation(program,name){const s=state(this),id=handle(s,program,'WebGLProgram');return id<0?null:wrap(s,'WebGLUniformLocation',native('getUniformLocation',s.id,id,str(name)));}
    uniform4f(loc,x,y,z,w){const s=state(this),id=handle(s,loc,'WebGLUniformLocation',true);if(id>=0)native('uniform4f',s.id,id,real(x),real(y),real(z),real(w));}
    createBuffer(){const s=state(this);return wrap(s,'WebGLBuffer',native('createBuffer',s.id));}
    bindBuffer(target,buffer){const s=state(this),id=handle(s,buffer,'WebGLBuffer',true);if(id>=0)native('bindBuffer',s.id,enum32(target),id);}
    bufferData(target,data,usage){const s=state(this);if(data===null){error(s,0x0501);return;}native('bufferData',s.id,enum32(target),data,enum32(usage));}
    bufferSubData(target,offset,data){native('bufferSubData',state(this).id,enum32(target),enum32(offset),data);}
    deleteBuffer(buffer){const s=state(this),id=handle(s,buffer,'WebGLBuffer',true);if(id>=0)native('deleteBuffer',s.id,id);}
    enableVertexAttribArray(index){native('enableVertexAttribArray',state(this).id,enum32(index));}
    disableVertexAttribArray(index){native('disableVertexAttribArray',state(this).id,enum32(index));}
    vertexAttribPointer(index,size,type,normalized,stride,offset){native('vertexAttribPointer',state(this).id,enum32(index),enum32(size),enum32(type),!!normalized,enum32(stride),enum32(offset));}
    drawArrays(mode,first,count){native('drawArrays',state(this).id,enum32(mode),enum32(first),enum32(count));}
    drawElements(mode,count,type,offset){native('drawElements',state(this).id,enum32(mode),enum32(count),enum32(type),enum32(offset));}
    readPixels(x,y,w,h,format,type,dest){native('readPixels',state(this).id,enum32(x),enum32(y),enum32(w),enum32(h),enum32(format),enum32(type),dest);}
  }
  const constants={NO_ERROR:0,INVALID_ENUM:0x500,INVALID_VALUE:0x501,INVALID_OPERATION:0x502,OUT_OF_MEMORY:0x505,
    POINTS:0,LINES:1,LINE_LOOP:2,LINE_STRIP:3,TRIANGLES:4,TRIANGLE_STRIP:5,TRIANGLE_FAN:6,
    ARRAY_BUFFER:0x8892,ELEMENT_ARRAY_BUFFER:0x8893,STATIC_DRAW:0x88e4,DYNAMIC_DRAW:0x88e8,STREAM_DRAW:0x88e0,
    FLOAT:0x1406,UNSIGNED_BYTE:0x1401,UNSIGNED_SHORT:0x1403,UNSIGNED_INT:0x1405,
    VERTEX_SHADER:0x8b31,FRAGMENT_SHADER:0x8b30,COMPILE_STATUS:0x8b81,LINK_STATUS:0x8b82,DELETE_STATUS:0x8b80,SHADER_TYPE:0x8b4f,
    ACTIVE_UNIFORMS:0x8b86,ACTIVE_ATTRIBUTES:0x8b89,COLOR_BUFFER_BIT:0x4000,DEPTH_BUFFER_BIT:0x100,STENCIL_BUFFER_BIT:0x400,
    RGBA:0x1908,RGB:0x1907,VERSION:0x1f02,VENDOR:0x1f00,RENDERER:0x1f01,SHADING_LANGUAGE_VERSION:0x8b8c,
    MAX_VERTEX_ATTRIBS:0x8869,MAX_TEXTURE_SIZE:0x0d33,MAX_RENDERBUFFER_SIZE:0x84e8,
    DEPTH_TEST:0x0b71,BLEND:0x0be2,CULL_FACE:0x0b44,DITHER:0x0bd0,SCISSOR_TEST:0x0c11,
    NEVER:0x200,LESS:0x201,EQUAL:0x202,LEQUAL:0x203,GREATER:0x204,NOTEQUAL:0x205,GEQUAL:0x206,ALWAYS:0x207};
  for(const [name,value] of Object.entries(constants))for(const object of [WebGLRenderingContext,WebGLRenderingContext.prototype])
    Object.defineProperty(object,name,{value,enumerable:true});
  Object.defineProperties(globalThis,{OffscreenCanvas:{value:OffscreenCanvas,writable:true,configurable:true},
    WebGLRenderingContext:{value:WebGLRenderingContext,writable:true,configurable:true}});
})(globalThis.__zeroGraphicsNative);
