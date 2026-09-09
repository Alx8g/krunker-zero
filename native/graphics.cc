#include "graphics.h"
#include "host.h"
#include "platform.h"
#ifdef _WIN32
#include "win32_window.h"
#endif
#include <algorithm>
#include <array>
#include <cmath>
#include <cstring>
#include <deque>
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

#ifdef _WIN32
#define ZERO_GL_CALL __stdcall
#else
#define ZERO_GL_CALL
#endif

namespace zero {
namespace {
// The small public EGL/GLES ABI slice we use. No vendored renderer or browser.
// Constants/signatures: Khronos EGL 1.5 and OpenGL ES 2.0 registries.
using EDisplay=void*; using EConfig=void*; using ESurface=void*; using EContext=void*;
using Enum=unsigned; using UInt=unsigned; using Int=int; using Size=int;
using Bool=unsigned char; using Bits=unsigned; using Float=float; using Ptr=std::ptrdiff_t;
constexpr Enum INVALID_ENUM=0x0500, INVALID_VALUE=0x0501, INVALID_OPERATION=0x0502, OUT_OF_MEMORY=0x0505;
constexpr Enum ARRAY_BUFFER=0x8892, ELEMENT_BUFFER=0x8893, FLOAT=0x1406;
constexpr std::size_t MAX_BYTES=64*1024*1024, MAX_OBJECTS=4096;
constexpr int MAX_DIMENSION=2048, MAX_CONTEXTS=8;
struct Api {
  platform::SharedLibrary lib, gles;
  bool loaded=false;
  std::string load_failure;
  using Proc = void (ZERO_GL_CALL *)();
  Proc (ZERO_GL_CALL *eglGetProcAddress)(const char*)=nullptr;
  EDisplay (ZERO_GL_CALL *eglGetPlatformDisplayEXT)(unsigned,void*,const int*)=nullptr;
  unsigned (ZERO_GL_CALL *eglInitialize)(EDisplay,int*,int*)=nullptr;
  unsigned (ZERO_GL_CALL *eglBindAPI)(unsigned)=nullptr;
  unsigned (ZERO_GL_CALL *eglChooseConfig)(EDisplay,const int*,EConfig*,int,int*)=nullptr;
  unsigned (ZERO_GL_CALL *eglGetConfigAttrib)(EDisplay,EConfig,int,int*)=nullptr;
  ESurface (ZERO_GL_CALL *eglCreatePbufferSurface)(EDisplay,EConfig,const int*)=nullptr;
  EContext (ZERO_GL_CALL *eglCreateContext)(EDisplay,EConfig,EContext,const int*)=nullptr;
  unsigned (ZERO_GL_CALL *eglMakeCurrent)(EDisplay,ESurface,ESurface,EContext)=nullptr;
  unsigned (ZERO_GL_CALL *eglDestroySurface)(EDisplay,ESurface)=nullptr;
  unsigned (ZERO_GL_CALL *eglDestroyContext)(EDisplay,EContext)=nullptr;
  unsigned (ZERO_GL_CALL *eglTerminate)(EDisplay)=nullptr;
#ifdef _WIN32
  ESurface (ZERO_GL_CALL *eglCreateWindowSurface)(EDisplay,EConfig,void*,const int*)=nullptr;
  unsigned (ZERO_GL_CALL *eglSwapBuffers)(EDisplay,ESurface)=nullptr;
  unsigned (ZERO_GL_CALL *eglSwapInterval)(EDisplay,int)=nullptr;
  unsigned (ZERO_GL_CALL *eglQuerySurface)(EDisplay,ESurface,int,int*)=nullptr;
#endif
#define GL_FUNCTIONS(X) \
  X(const unsigned char*,GetString,(Enum)) \
  X(void,GetIntegerv,(Enum,Int*)) X(void,GetFloatv,(Enum,Float*)) \
  X(Enum,GetError,()) X(void,Viewport,(Int,Int,Size,Size)) \
  X(void,ClearColor,(Float,Float,Float,Float)) X(void,ClearDepthf,(Float)) \
  X(void,Clear,(Bits)) X(void,Finish,()) X(void,Flush,()) \
  X(void,ReadPixels,(Int,Int,Size,Size,Enum,Enum,void*)) \
  X(void,Enable,(Enum)) X(void,Disable,(Enum)) X(Bool,IsEnabled,(Enum)) \
  X(void,DepthFunc,(Enum)) X(void,DepthMask,(Bool)) X(void,ColorMask,(Bool,Bool,Bool,Bool)) \
  X(UInt,CreateShader,(Enum)) X(void,ShaderSource,(UInt,Size,const char*const*,const Int*)) \
  X(void,CompileShader,(UInt)) X(void,GetShaderiv,(UInt,Enum,Int*)) \
  X(void,GetShaderInfoLog,(UInt,Size,Size*,char*)) X(void,DeleteShader,(UInt)) \
  X(UInt,CreateProgram,()) X(void,AttachShader,(UInt,UInt)) X(void,LinkProgram,(UInt)) \
  X(void,GetProgramiv,(UInt,Enum,Int*)) X(void,GetProgramInfoLog,(UInt,Size,Size*,char*)) \
  X(void,UseProgram,(UInt)) X(void,DeleteProgram,(UInt)) \
  X(Int,GetAttribLocation,(UInt,const char*)) X(Int,GetUniformLocation,(UInt,const char*)) \
  X(void,Uniform4f,(Int,Float,Float,Float,Float)) \
  X(void,GenBuffers,(Size,UInt*)) X(void,DeleteBuffers,(Size,const UInt*)) \
  X(void,BindBuffer,(Enum,UInt)) X(void,BufferData,(Enum,Ptr,const void*,Enum)) \
  X(void,BufferSubData,(Enum,Ptr,Ptr,const void*)) \
  X(void,EnableVertexAttribArray,(UInt)) X(void,DisableVertexAttribArray,(UInt)) \
  X(void,VertexAttribPointer,(UInt,Int,Enum,Bool,Size,const void*)) \
  X(void,DrawArrays,(Enum,Int,Size)) X(void,DrawElements,(Enum,Size,Enum,const void*))
#define DECL(ret,name,args) ret (ZERO_GL_CALL *gl##name)args=nullptr;
  GL_FUNCTIONS(DECL)
#undef DECL
  template<class T> void Symbol(T& out,const char* name,bool gl=false) {
    auto p = gl ? gles.Find(name) : lib.Find(name);
    if (gl && !p) {
      const auto proc = eglGetProcAddress(name);
      static_assert(sizeof(p) == sizeof(proc));
      std::memcpy(&p, &proc, sizeof(p));
    }
    if(!p) throw std::runtime_error(std::string("required graphics entry point absent: ")+name);
    static_assert(sizeof(out)==sizeof(p)); std::memcpy(&out,&p,sizeof(p));
  }
  void Load() {
    if(loaded) return;
    if(!load_failure.empty()) throw std::runtime_error(load_failure);
    try {
#ifdef _WIN32
    const auto directory = platform::ExecutableDirectory();
    // Both DLLs must come from one deliberate, app-local ANGLE installation.
    // Load GLES first because the EGL dispatch library may import it.
    gles.Open(directory / "libGLESv2.dll");
    lib.Open(directory / "libEGL.dll");
#else
    lib.OpenSystem("libEGL.so.1");
#endif
    Symbol(eglGetProcAddress,"eglGetProcAddress");
#define EGL_BIND(name) Symbol(name,#name)
    EGL_BIND(eglInitialize); EGL_BIND(eglBindAPI); EGL_BIND(eglChooseConfig); EGL_BIND(eglGetConfigAttrib);
    EGL_BIND(eglCreatePbufferSurface); EGL_BIND(eglCreateContext); EGL_BIND(eglMakeCurrent);
    EGL_BIND(eglDestroySurface); EGL_BIND(eglDestroyContext); EGL_BIND(eglTerminate);
#ifdef _WIN32
    EGL_BIND(eglCreateWindowSurface); EGL_BIND(eglSwapBuffers); EGL_BIND(eglSwapInterval); EGL_BIND(eglQuerySurface);
#endif
#undef EGL_BIND
    Symbol(eglGetPlatformDisplayEXT,"eglGetPlatformDisplayEXT",true);
#define LOAD(ret,name,args) Symbol(gl##name,"gl" #name,true);
    GL_FUNCTIONS(LOAD)
#undef LOAD
    loaded=true;
    } catch(const std::exception& e) {
      load_failure=e.what();
      throw;
    }
  }
};
struct Resource {
  enum Kind { Buffer, Shader, Program, Uniform } kind;
  explicit Resource(Kind type):kind(type){}
  UInt name=0; bool deleted=false; Enum target=0;
  std::vector<unsigned char> bytes;
  unsigned owner=0, generation=0; Int location=-1;
};
struct Attribute {bool enabled=false; unsigned buffer=0; int size=4,stride=0; std::size_t offset=0;};
struct Context {
  bool window_surface=false;
  ESurface surface=nullptr; EContext context=nullptr; int width=0,height=0;
  unsigned next=1,array=0,elements=0,program=0;
  std::size_t allocated=0; std::map<unsigned,Resource> objects;
  std::vector<Attribute> attributes; std::deque<Enum> errors;
  std::string renderer,version;
  void Error(Enum e) { if(e && std::find(errors.begin(),errors.end(),e)==errors.end()) errors.push_back(e); }
};
v8::Local<v8::String> Str(v8::Isolate* i,const std::string& s) {
  return v8::String::NewFromUtf8(i,s.data(),v8::NewStringType::kNormal,static_cast<int>(s.size())).ToLocalChecked();
}
std::string Text(v8::Isolate* i,v8::Local<v8::Value> v) {
  if(!v->IsString()) throw std::invalid_argument("native graphics expected string");
  if(v.As<v8::String>()->Length()>1024*1024) throw std::invalid_argument("graphics string exceeds 1 MiB code units");
  v8::String::Utf8Value t(i,v); if(!*t) throw std::runtime_error("string conversion failed");
  return std::string(*t,t.length());
}
double Number(v8::Local<v8::Value> v) {
  if(!v->IsNumber() || !std::isfinite(v.As<v8::Number>()->Value()))
    throw std::invalid_argument("native graphics expected finite number");
  return v.As<v8::Number>()->Value();
}
int Integer(v8::Local<v8::Value> v) {
  double n=Number(v);
  if(n!=std::trunc(n)||n<-2147483648.0||n>2147483647.0) throw std::invalid_argument("graphics integer outside int32");
  return static_cast<int>(n);
}
struct Bytes {
  std::shared_ptr<v8::BackingStore> backing; unsigned char* data=nullptr; std::size_t size=0;
  explicit Bytes(v8::Local<v8::Value> value) {
    v8::Local<v8::ArrayBuffer> b; std::size_t offset=0;
    if(value->IsArrayBufferView()) {
      auto v=value.As<v8::ArrayBufferView>(); b=v->Buffer(); offset=v->ByteOffset(); size=v->ByteLength();
    } else if(value->IsArrayBuffer()) {b=value.As<v8::ArrayBuffer>();size=b->ByteLength();}
    else throw std::invalid_argument("expected ArrayBuffer or ArrayBufferView");
    if(b->WasDetached()) throw std::invalid_argument("detached ArrayBuffer");
    backing=b->GetBackingStore();
    if(backing->IsShared()) throw std::invalid_argument("shared graphics buffers are not supported");
    if(offset>backing->ByteLength()||size>backing->ByteLength()-offset||size>MAX_BYTES)
      throw std::invalid_argument("graphics view exceeds backing store or cap");
    data=static_cast<unsigned char*>(backing->Data()); if(data) data+=offset;
  }
};
}
struct Graphics::Impl {
  v8::Isolate* isolate; std::string requested_backend; bool window_enabled; unsigned swap_interval; Api api; EDisplay display=nullptr; EConfig config=nullptr;
  std::vector<std::unique_ptr<Context>> contexts;
  std::size_t draws=0,reads=0,compiles=0,uploaded=0; std::string last_error;
  std::size_t presented=0;
#ifdef _WIN32
  std::unique_ptr<Win32Window> window;
#endif
  bool initialized=false;
  std::string init_failure;
  explicit Impl(v8::Isolate* i, const Options& options):isolate(i),requested_backend(options.angle_backend),window_enabled(options.window),swap_interval(options.swap_interval){}
  ~Impl(){
    if(display) {
      api.eglMakeCurrent(display,nullptr,nullptr,nullptr);
      for(auto& c:contexts) {if(c->context) api.eglDestroyContext(display,c->context);
                            if(c->surface) api.eglDestroySurface(display,c->surface);}
      api.eglTerminate(display);
    }
  }
  void Init(){
    if(initialized) return;
    if(!init_failure.empty()) throw std::runtime_error(init_failure);
    try {
    api.Load();
#ifdef _WIN32
    // EGL_ANGLE_platform_angle + EGL_ANGLE_platform_angle_d3d. Explicit device
    // selection: hardware never silently falls back to WARP or a no-op driver.
    const int attributes[] = {0x3203, 0x3208, 0x3209,
        requested_backend == "warp" ? 0x320B : 0x320A, 0x3038};
    auto candidate=api.eglGetPlatformDisplayEXT(0x3202,nullptr,attributes);
#else
    auto candidate=api.eglGetPlatformDisplayEXT(0x31DD,nullptr,nullptr); // MESA surfaceless
#endif
    int major=0,minor=0;
    if(!candidate||!api.eglInitialize(candidate,&major,&minor)) throw std::runtime_error("requested EGL display initialization failed; no backend fallback");
    display=candidate;
    if(!api.eglBindAPI(0x30A0)) throw std::runtime_error("EGL OpenGL ES API unavailable");
    const int attrs[]={0x3033,window_enabled?5:1,0x3040,4,0x3024,8,0x3023,8,0x3022,8,0x3021,8,0x3025,16,0x3038};
    int n=0;
    if(!api.eglChooseConfig(display,attrs,nullptr,0,&n)||n<1||n>4096)
      throw std::runtime_error("EGL RGBA8/depth16 surface config unavailable");
    std::vector<EConfig> candidates(static_cast<std::size_t>(n));
    int count=0;
    if(!api.eglChooseConfig(display,attrs,candidates.data(),n,&count)||count<1||count>n)
      throw std::runtime_error("EGL config enumeration failed");
    // EGL attributes express MINIMUM sizes. Search for the exact supported
    // format instead of assuming the first driver-sorted result is suitable.
    for(int index=0;index<count;++index) {
      bool supported=true;
      for(int key : {0x3024,0x3023,0x3022,0x3021,0x3026,0x3032}) {
        int value=0;
        if(!api.eglGetConfigAttrib(display,candidates[index],key,&value) ||
            value!=(key==0x3026||key==0x3032?0:8)) supported=false;
      }
      if(supported){config=candidates[index];break;}
    }
    if(!config) throw std::runtime_error("EGL returned no exact RGBA8/no-stencil/no-multisample format");
    initialized=true;
    } catch(const std::exception& e) {
      init_failure=e.what();
      throw;
    }
  }
  ESurface Surface(int w,int h){
    const int a[]={0x3057,w,0x3056,h,0x3038};
    auto p=api.eglCreatePbufferSurface(display,config,a);
    if(!p) throw std::runtime_error("EGL pbuffer allocation failed");
    return p;
  }
  void Current(Context& c){if(!api.eglMakeCurrent(display,c.surface,c.surface,c.context)) throw std::runtime_error("EGL make-current failed");}
  void ClearNew(){
    Float color[4],depth;Int cm[4],dm;
    api.glGetFloatv(0x0C22,color);api.glGetFloatv(0x0B73,&depth);
    api.glGetIntegerv(0x0C23,cm);api.glGetIntegerv(0x0B72,&dm);
    Bool scissor=api.glIsEnabled(0x0C11);
    api.glDisable(0x0C11);api.glColorMask(1,1,1,1);api.glDepthMask(1);
    api.glClearColor(0,0,0,0);api.glClearDepthf(1);api.glClear(0x4000|0x0100);
    api.glClearColor(color[0],color[1],color[2],color[3]);api.glClearDepthf(depth);
    api.glColorMask(cm[0],cm[1],cm[2],cm[3]);api.glDepthMask(dm);
    if(scissor) api.glEnable(0x0C11);
  }
  unsigned Create(int w,int h,bool onscreen=false){
    if(w<1||h<1||w>MAX_DIMENSION||h>MAX_DIMENSION) throw std::invalid_argument("drawing buffer dimensions must be 1..2048");
    if(contexts.size()>=MAX_CONTEXTS) throw std::runtime_error("native context cap (8) reached");
    Init(); auto c=std::make_unique<Context>(); c->width=w;c->height=h;
#ifdef _WIN32
    std::unique_ptr<Win32Window> candidate;
    if (onscreen) {
      if (!window_enabled) throw std::invalid_argument("native window requires --window");
      if (window) throw std::invalid_argument("only one native fixture window is supported");
      candidate = std::make_unique<Win32Window>(w,h);
      c->surface=api.eglCreateWindowSurface(display,config,candidate->Handle(),nullptr);
      if(!c->surface) throw std::runtime_error("ANGLE window surface creation failed");
      c->window_surface=true;
    } else
#else
    if (onscreen) throw std::invalid_argument("native window is Windows-only");
#endif
    { c->surface=Surface(w,h); }
    const int attrs[]={0x3098,2,0x3038};
    c->context=api.eglCreateContext(display,config,nullptr,attrs);
    if(!c->context){api.eglDestroySurface(display,c->surface);throw std::runtime_error("EGL ES context creation failed");}
    try {
      Current(*c);
#ifdef _WIN32
      if (onscreen) {
        int actual_width=0,actual_height=0;
        if (!api.eglQuerySurface(display,c->surface,0x3057,&actual_width) ||
            !api.eglQuerySurface(display,c->surface,0x3056,&actual_height) ||
            actual_width!=w || actual_height!=h)
          throw std::runtime_error("Native window drawing buffer differs from requested size; check Windows DPI setup");
        if (!api.eglSwapInterval(display,static_cast<int>(swap_interval)))
          throw std::runtime_error("ANGLE could not apply requested swap interval");
      }
#endif
      Int n=0;api.glGetIntegerv(0x8869,&n);
      if(n<1||n>256) throw std::runtime_error("invalid vertex attribute limit");
      c->attributes.resize(n);
      auto text=[&](Enum p){auto t=api.glGetString(p);return t?std::string(reinterpret_cast<const char*>(t)):std::string();};
      c->renderer=text(0x1F01);c->version=text(0x1F02);ClearNew();api.glViewport(0,0,w,h);
    } catch(...) {api.eglDestroyContext(display,c->context);api.eglDestroySurface(display,c->surface);throw;}
    contexts.push_back(std::move(c));
#ifdef _WIN32
    if(candidate) window=std::move(candidate);
#endif
    return static_cast<unsigned>(contexts.size());
  }
  Resource* Obj(Context& c,unsigned id,Resource::Kind kind,bool allow_deleted=false){
    auto it=c.objects.find(id);
    if(it==c.objects.end()||it->second.kind!=kind||(!allow_deleted&&it->second.deleted)) {c.Error(INVALID_OPERATION);return nullptr;}
    return &it->second;
  }
  unsigned Add(Context& c,Resource r){
    if(c.objects.size()>=MAX_OBJECTS){c.Error(OUT_OF_MEMORY);return 0;}
    unsigned id=c.next++;c.objects.emplace(id,std::move(r));return id;
  }
  bool ErrorFree(Context& c){bool ok=true;for(int n=0;n<16;++n){Enum e=api.glGetError();if(!e)break;c.Error(e);ok=false;}return ok;}
  bool Vertices(Context& c,std::size_t max_index){
    if(!c.program){c.Error(INVALID_OPERATION);return false;}
    auto* p=Obj(c,c.program,Resource::Program,true);if(!p)return false;
    Int linked=0;api.glGetProgramiv(p->name,0x8B82,&linked);
    if(!linked){c.Error(INVALID_OPERATION);return false;}
    for(auto& a:c.attributes) if(a.enabled){
      auto* b=Obj(c,a.buffer,Resource::Buffer);if(!b)return false;
      std::uint64_t stride=a.stride?a.stride:a.size*4;
      std::uint64_t end=a.offset+max_index*stride+a.size*4;
      if(end>b->bytes.size()){c.Error(INVALID_OPERATION);return false;}
    }
    return true;
  }
  static void Call(const v8::FunctionCallbackInfo<v8::Value>& a){
    auto* self=static_cast<Impl*>(a.Data().As<v8::External>()->Value());
    try {self->Dispatch(a);}catch(const std::exception& e){
      self->last_error=e.what();a.GetIsolate()->ThrowException(v8::Exception::Error(Str(a.GetIsolate(),e.what())));
    }
  }
  void Dispatch(const v8::FunctionCallbackInfo<v8::Value>& a){
    if(a.Length()<1)throw std::invalid_argument("missing graphics operation");
    auto op=Text(isolate,a[0]);auto ret=a.GetReturnValue();
    auto num=[&](int n){return Number(a[n]);};auto in=[&](int n){return Integer(a[n]);};
    if(op=="windowEnabled"){ret.Set(window_enabled);return;}
    if(op=="create"){ret.Set(Create(in(1),in(2)));return;}
#ifdef _WIN32
    if(op=="createWindow"){ret.Set(Create(in(1),in(2),true));return;}
    if(op=="windowEvents" || op=="closeWindow" || op=="capturePointer") {
      if(!window) throw std::invalid_argument("native fixture window has not been created");
      if(op=="closeWindow"){window->Close();return;}
      if(op=="capturePointer"){ret.Set(window->CapturePointer(a[1]->BooleanValue(isolate)));return;}
      const auto events=window->DrainEvents();
      auto values=v8::Array::New(isolate,static_cast<int>(events.size()));
      const auto current=isolate->GetCurrentContext();
      for(std::size_t index=0;index<events.size();++index) {
        const auto& event=events[index];auto value=v8::Object::New(isolate);
        if(!value->CreateDataProperty(current,Str(isolate,"type"),Str(isolate,event.type)).FromMaybe(false))return;
        if(!value->CreateDataProperty(current,Str(isolate,"x"),v8::Integer::New(isolate,event.x)).FromMaybe(false))return;
        if(!value->CreateDataProperty(current,Str(isolate,"y"),v8::Integer::New(isolate,event.y)).FromMaybe(false))return;
        if(!value->CreateDataProperty(current,Str(isolate,"code"),v8::Integer::New(isolate,event.code)).FromMaybe(false))return;
        if(!value->CreateDataProperty(current,Str(isolate,"repeat"),v8::Boolean::New(isolate,event.repeat)).FromMaybe(false))return;
        if(!values->CreateDataProperty(current,static_cast<unsigned>(index),value).FromMaybe(false))return;
      }
      ret.Set(values);return;
    }
#endif
    if(a.Length()<2)throw std::invalid_argument("missing context");
    int cid=in(1);
    if(cid<1||static_cast<std::size_t>(cid)>contexts.size()) throw std::invalid_argument("unknown context");
    auto& c=*contexts[cid-1];Current(c);
#ifdef _WIN32
    if(op=="present") {
      if(!c.window_surface || !window) throw std::invalid_argument("present requires the native window canvas");
      if(window->Closed() || window->Minimized()) {ret.Set(false);return;}
      if(!api.eglSwapBuffers(display,c.surface)) throw std::runtime_error("ANGLE swap failed");
      ++presented;ret.Set(true);return;
    }
#endif
    if(op=="error"){c.Error(in(2));return;}
    if(op=="getError") {ErrorFree(c);Enum e=0;if(!c.errors.empty()){e=c.errors.front();c.errors.pop_front();}ret.Set(e);return;}
    if(op=="resize"){
      if(c.window_surface) throw std::invalid_argument("native fixture window resizing is not implemented");
      int w=in(2),h=in(3);if(w<1||h<1||w>MAX_DIMENSION||h>MAX_DIMENSION) throw std::invalid_argument("drawing buffer dimensions must be 1..2048");
      auto next=Surface(w,h);auto prev=c.surface;c.surface=next;
      if(!api.eglMakeCurrent(display,next,next,c.context)){c.surface=prev;api.eglDestroySurface(display,next);throw std::runtime_error("resize make-current failed");}
      api.eglDestroySurface(display,prev);c.width=w;c.height=h;ClearNew();return;
    }
    if(op=="getParameter"){
      Enum p=in(2);
      if(p==0x1F00||p==0x1F01||p==0x1F02||p==0x8B8C){auto s=api.glGetString(p);if(s)ret.Set(Str(isolate,reinterpret_cast<const char*>(s)));else ret.Set(v8::Null(isolate));return;}
      if(p==0x8869||p==0x0D33||p==0x84E8){Int n=0;api.glGetIntegerv(p,&n);ret.Set(n);return;}
      c.Error(INVALID_ENUM);ret.Set(v8::Null(isolate));return;
    }
    if(op=="viewport"){int w=in(4),h=in(5);if(w<0||h<0){c.Error(INVALID_VALUE);return;}api.glViewport(in(2),in(3),w,h);return;}
    if(op=="clearColor"){api.glClearColor(num(2),num(3),num(4),num(5));return;}
    if(op=="clearDepth"){api.glClearDepthf(num(2));return;}
    if(op=="clear"){unsigned mask=in(2);if(mask&~(0x4000u|0x100u|0x400u)){c.Error(INVALID_VALUE);return;}api.glClear(mask);return;}
    if(op=="finish"){api.glFinish();return;}if(op=="flush"){api.glFlush();return;}
    if(op=="enable"||op=="disable"){
      Enum cap=in(2);if(cap!=0x0B71&&cap!=0x0BE2&&cap!=0x0B44&&cap!=0x0BD0&&cap!=0x0C11){c.Error(INVALID_ENUM);return;}
      if(op=="enable")api.glEnable(cap);else api.glDisable(cap);return;
    }
    if(op=="depthFunc"){api.glDepthFunc(in(2));return;}
    if(op=="depthMask"){api.glDepthMask(a[2]->IsTrue());return;}
    if(op=="colorMask"){api.glColorMask(a[2]->IsTrue(),a[3]->IsTrue(),a[4]->IsTrue(),a[5]->IsTrue());return;}
    if(op=="createShader"||op=="createProgram"||op=="createBuffer"){
      if(c.objects.size()>=MAX_OBJECTS){c.Error(OUT_OF_MEMORY);ret.Set(0);return;}
      Resource r{op=="createShader"?Resource::Shader:op=="createProgram"?Resource::Program:Resource::Buffer};
      if(r.kind==Resource::Shader){Enum type=in(2);if(type!=0x8B31&&type!=0x8B30){c.Error(INVALID_ENUM);ret.Set(0);return;}r.name=api.glCreateShader(type);r.target=type;}
      else if(r.kind==Resource::Program)r.name=api.glCreateProgram();else api.glGenBuffers(1,&r.name);
      if(!r.name){c.Error(OUT_OF_MEMORY);ret.Set(0);return;}ret.Set(Add(c,std::move(r)));return;
    }
    if(op=="shaderSource"||op=="compileShader"||op=="getShaderParameter"||op=="getShaderInfoLog"||op=="deleteShader"){
      if(op=="deleteShader"&&in(2)==0)return;
      auto* s=Obj(c,in(2),Resource::Shader,op=="deleteShader"||op=="getShaderParameter");if(!s){ret.Set(v8::Null(isolate));return;}
      if(op=="shaderSource"){auto text=Text(isolate,a[3]);const char* p=text.data();int len=text.size();api.glShaderSource(s->name,1,&p,&len);return;}
      if(op=="compileShader"){api.glCompileShader(s->name);++compiles;return;}
      if(op=="getShaderParameter"){
        Enum p=in(3);if(p!=0x8B81&&p!=0x8B80&&p!=0x8B4F){c.Error(INVALID_ENUM);ret.Set(v8::Null(isolate));return;}
        if(p==0x8B80){ret.Set(s->deleted);return;}
        if(s->deleted){c.Error(INVALID_VALUE);ret.Set(v8::Null(isolate));return;}
        Int n=0;api.glGetShaderiv(s->name,p,&n);if(p==0x8B4F)ret.Set(n);else ret.Set(n!=0);return;
      }
      if(op=="getShaderInfoLog"){std::vector<char> log(65536);Int n=0;api.glGetShaderInfoLog(s->name,log.size(),&n,log.data());ret.Set(Str(isolate,std::string(log.data(),std::clamp(n,0,static_cast<int>(log.size())-1))));return;}
      if(!s->deleted){api.glDeleteShader(s->name);s->deleted=true;}return;
    }
    if(op=="deleteBuffer"){
      unsigned id=in(2);if(!id)return;auto* b=Obj(c,id,Resource::Buffer,true);if(!b)return;
      if(!b->deleted){api.glDeleteBuffers(1,&b->name);b->deleted=true;c.allocated-=b->bytes.size();std::vector<unsigned char>().swap(b->bytes);
        if(c.array==id)c.array=0;
        if(c.elements==id)c.elements=0;
        for(auto& v:c.attributes)if(v.buffer==id)v.buffer=0;}
      return;
    }
    if(op=="bindBuffer"){
      Enum target=in(2);if(target!=ARRAY_BUFFER&&target!=ELEMENT_BUFFER){c.Error(INVALID_ENUM);return;}
      unsigned id=in(3);Resource* b=id?Obj(c,id,Resource::Buffer):nullptr;if(id&&!b)return;
      if(b&&b->target&&b->target!=target){c.Error(INVALID_OPERATION);return;}
      api.glBindBuffer(target,b?b->name:0);if(b)b->target=target;
      (target==ARRAY_BUFFER?c.array:c.elements)=id;return;
    }
    if(op=="bufferData"||op=="bufferSubData"){
      Enum target=in(2);if(target!=ARRAY_BUFFER&&target!=ELEMENT_BUFFER){c.Error(INVALID_ENUM);return;}
      auto* b=Obj(c,target==ARRAY_BUFFER?c.array:c.elements,Resource::Buffer);if(!b)return;
      if(op=="bufferData"){
        Enum usage=in(4);if(usage!=0x88E0&&usage!=0x88E4&&usage!=0x88E8){c.Error(INVALID_ENUM);return;}
        std::vector<unsigned char> bytes;
        if(a[3]->IsNumber()){double size=num(3);if(size<0||size!=std::trunc(size)){c.Error(INVALID_VALUE);return;}
          if(size>MAX_BYTES){c.Error(OUT_OF_MEMORY);return;}bytes.resize(static_cast<std::size_t>(size),0);
        }else{Bytes src(a[3]);if(src.size)bytes.assign(src.data,src.data+src.size);}
        if(bytes.size()>MAX_BYTES-(c.allocated-b->bytes.size())){c.Error(OUT_OF_MEMORY);return;}
        ErrorFree(c);api.glBufferData(target,bytes.size(),bytes.empty()?nullptr:bytes.data(),usage);
        if(!ErrorFree(c))return;
        c.allocated=c.allocated-b->bytes.size()+bytes.size();uploaded+=bytes.size();b->bytes=std::move(bytes);return;
      }
      int offset=in(3);if(offset<0){c.Error(INVALID_VALUE);return;}Bytes src(a[4]);
      if(static_cast<std::size_t>(offset)>b->bytes.size()||src.size>b->bytes.size()-offset){c.Error(INVALID_VALUE);return;}
      if(src.size){ErrorFree(c);api.glBufferSubData(target,offset,src.size,src.data);if(!ErrorFree(c))return;std::memcpy(b->bytes.data()+offset,src.data,src.size);uploaded+=src.size;}return;
    }
    if(op=="useProgram"||op=="attachShader"||op=="linkProgram"||op=="getProgramParameter"||op=="getProgramInfoLog"||op=="getAttribLocation"||op=="getUniformLocation"||op=="deleteProgram"){
      unsigned id=in(2);if(op=="useProgram"&&!id){api.glUseProgram(0);c.program=0;return;}if(op=="deleteProgram"&&!id)return;
      auto* p=Obj(c,id,Resource::Program,op=="deleteProgram"||op=="getProgramParameter");if(!p){ret.Set(v8::Null(isolate));return;}
      if(op=="useProgram"){ErrorFree(c);api.glUseProgram(p->name);if(ErrorFree(c))c.program=id;return;}
      if(op=="attachShader"){auto* s=Obj(c,in(3),Resource::Shader);if(s)api.glAttachShader(p->name,s->name);return;}
      if(op=="linkProgram"){api.glLinkProgram(p->name);++p->generation;return;}
      if(op=="deleteProgram"){if(!p->deleted){api.glDeleteProgram(p->name);p->deleted=true;}return;}
      if(op=="getProgramParameter"){
        Enum key=in(3);if(key==0x8B80){ret.Set(p->deleted);return;}
        if(p->deleted){c.Error(INVALID_VALUE);ret.Set(v8::Null(isolate));return;}
        if(key!=0x8B82&&key!=0x8B89&&key!=0x8B86){c.Error(INVALID_ENUM);ret.Set(v8::Null(isolate));return;}
        Int n=0;api.glGetProgramiv(p->name,key,&n);if(key==0x8B82)ret.Set(n!=0);else ret.Set(n);return;
      }
      if(op=="getProgramInfoLog"){std::vector<char> log(65536);Int n=0;api.glGetProgramInfoLog(p->name,log.size(),&n,log.data());ret.Set(Str(isolate,std::string(log.data(),std::clamp(n,0,static_cast<int>(log.size())-1))));return;}
      auto name=Text(isolate,a[3]);if(name.find('\0')!=std::string::npos){c.Error(INVALID_VALUE);ret.Set(op=="getAttribLocation"?-1:0);return;}
      Int linked=0;api.glGetProgramiv(p->name,0x8B82,&linked);if(!linked){c.Error(INVALID_OPERATION);ret.Set(op=="getAttribLocation"?-1:0);return;}
      if(op=="getAttribLocation"){ret.Set(api.glGetAttribLocation(p->name,name.c_str()));return;}
      Int loc=api.glGetUniformLocation(p->name,name.c_str());if(loc<0){ret.Set(0);return;}
      Resource u{Resource::Uniform};u.owner=id;u.generation=p->generation;u.location=loc;ret.Set(Add(c,std::move(u)));return;
    }
    if(op=="uniform4f"){
      unsigned id=in(2);if(!id)return;auto* u=Obj(c,id,Resource::Uniform);if(!u)return;
      auto* p=Obj(c,c.program,Resource::Program,true);
      if(!p||u->owner!=c.program||u->generation!=p->generation){c.Error(INVALID_OPERATION);return;}
      api.glUniform4f(u->location,num(3),num(4),num(5),num(6));return;
    }
    if(op=="enableVertexAttribArray"||op=="disableVertexAttribArray"||op=="vertexAttribPointer"){
      int index=in(2);if(index<0||static_cast<std::size_t>(index)>=c.attributes.size()){c.Error(INVALID_VALUE);return;}
      auto& v=c.attributes[index];
      if(op=="enableVertexAttribArray"){api.glEnableVertexAttribArray(index);v.enabled=true;return;}
      if(op=="disableVertexAttribArray"){api.glDisableVertexAttribArray(index);v.enabled=false;return;}
      int size=in(3),type=in(4),stride=in(6),offset=in(7);
      if(type!=FLOAT){c.Error(INVALID_ENUM);return;}
      if(size<1||size>4||stride<0||stride>255||offset<0){c.Error(INVALID_VALUE);return;}
      if((stride%4)||(offset%4)||!c.array){c.Error(INVALID_OPERATION);return;}
      api.glVertexAttribPointer(index,size,type,a[5]->IsTrue(),stride,reinterpret_cast<const void*>(static_cast<std::uintptr_t>(offset)));
      v.buffer=c.array;v.size=size;v.stride=stride;v.offset=offset;return;
    }
    if(op=="drawArrays"||op=="drawElements"){
      int mode=in(2);if(mode<0||mode>6){c.Error(INVALID_ENUM);return;}
      if(op=="drawArrays"){
        int first=in(3),count=in(4);if(first<0||count<0){c.Error(INVALID_VALUE);return;}if(!count)return;
        if(!Vertices(c,static_cast<std::size_t>(first)+count-1))return;
        ErrorFree(c);api.glDrawArrays(mode,first,count);if(ErrorFree(c))++draws;return;
      }
      int count=in(3),type=in(4),offset=in(5);if(count<0||offset<0){c.Error(INVALID_VALUE);return;}
      if(type!=0x1401&&type!=0x1403){c.Error(INVALID_ENUM);return;}int size=type==0x1403?2:1;
      if(offset%size){c.Error(INVALID_OPERATION);return;}auto* b=Obj(c,c.elements,Resource::Buffer);if(!b)return;
      if(static_cast<std::size_t>(offset)>b->bytes.size()||static_cast<std::size_t>(count)*size>b->bytes.size()-offset){c.Error(INVALID_OPERATION);return;}if(!count)return;
      unsigned max=0;for(int i=0;i<count;++i){unsigned value=b->bytes[offset+i*size];if(size==2){std::uint16_t val;std::memcpy(&val,b->bytes.data()+offset+i*size,2);value=val;}max=std::max(max,value);}
      if(!Vertices(c,max))return;
      ErrorFree(c);api.glDrawElements(mode,count,type,reinterpret_cast<const void*>(static_cast<std::uintptr_t>(offset)));if(ErrorFree(c))++draws;return;
    }
    if(op=="readPixels"){
      int x=in(2),y=in(3),w=in(4),h=in(5);Enum format=in(6),type=in(7);
      if(w<0||h<0){c.Error(INVALID_VALUE);return;}
      if(format!=0x1908||type!=0x1401){c.Error(INVALID_ENUM);return;}
      if(!a[8]->IsUint8Array()){c.Error(INVALID_OPERATION);return;}
      Bytes dest(a[8]);std::uint64_t needed=std::uint64_t(w)*h*4;
      if(needed>MAX_BYTES||needed>dest.size){c.Error(INVALID_OPERATION);return;}if(!needed)return;
      std::memset(dest.data,0,needed);
      auto x0=std::max<std::int64_t>(0,x),y0=std::max<std::int64_t>(0,y);
      auto x1=std::min<std::int64_t>(c.width,std::int64_t(x)+w),y1=std::min<std::int64_t>(c.height,std::int64_t(y)+h);
      if(x1>x0&&y1>y0){std::vector<unsigned char> pixels((x1-x0)*(y1-y0)*4,0);
        api.glReadPixels(x0,y0,x1-x0,y1-y0,format,type,pixels.data());
        for(auto row=y0;row<y1;++row)std::memcpy(dest.data+((row-y)*w+(x0-x))*4,pixels.data()+(row-y0)*(x1-x0)*4,(x1-x0)*4);
      }++reads;return;
    }
    throw std::invalid_argument("unimplemented graphics operation: "+op);
  }
};
Graphics::Graphics(v8::Isolate* isolate, const Options& options):impl_(std::make_unique<Impl>(isolate, options)){}
Graphics::~Graphics()=default;
void Graphics::PumpEvents() {
#ifdef _WIN32
  if(impl_->window) impl_->window->Pump();
#endif
}
bool Graphics::WindowClosed() const {
#ifdef _WIN32
  return impl_->window && impl_->window->Closed();
#else
  return false;
#endif
}
void Graphics::Bind(v8::Local<v8::Context> c){
  auto i=c->GetIsolate();c->Global()->Set(c,Str(i,"__zeroGraphicsNative"),v8::Function::New(c,Impl::Call,v8::External::New(i,impl_.get())).ToLocalChecked()).Check();
}
std::string Graphics::ReportJson()const {
  auto& g=*impl_;std::ostringstream o;
  std::size_t shadow_bytes=0,shadow_capacity=0;
  for(const auto& c:g.contexts) for(const auto& entry:c->objects) {
    shadow_bytes+=entry.second.bytes.size();shadow_capacity+=entry.second.bytes.capacity();
  }
#ifdef _WIN32
  const std::string backend = std::string(g.requested_backend == "warp" ? "angle-warp" : "angle-d3d11") + (g.window ? "-window" : "-pbuffer");
#else
  const std::string backend = "egl-surfaceless-pbuffer";
#endif
  o<<"{\"backend\":"<<JsonString(backend)<<",\"experimental_subset\":true,\"presented_frames\":"<<g.presented<<",\"contexts\":"<<g.contexts.size()
   <<",\"draw_calls\":"<<g.draws<<",\"shader_compiles\":"<<g.compiles<<",\"pixel_reads\":"<<g.reads<<",\"bytes_uploaded\":"<<g.uploaded
   <<",\"cpu_shadow_bytes\":"<<shadow_bytes<<",\"cpu_shadow_capacity_bytes\":"<<shadow_capacity
#ifdef _WIN32
   <<",\"window_created\":"<<(g.window?"true":"false")
   <<",\"input_events_dropped\":"<<(g.window?g.window->DroppedEvents():0)
#endif
   <<",\"last_error\":"<<JsonString(g.last_error)<<",\"devices\":[";
  bool first=true;for(auto& c:g.contexts){if(!first)o<<',';first=false;o<<"{\"renderer\":"<<JsonString(c->renderer)<<",\"version\":"<<JsonString(c->version)<<",\"width\":"<<c->width<<",\"height\":"<<c->height<<'}';}
  return o.str()+"]}";
}
}
