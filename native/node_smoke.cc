// DEVELOPMENT-ONLY adapter. Never linked into the standalone zero executable.
// This lets an offline development machine exercise native V8 bindings using
// an already-installed Node/V8. Run once per child process: Run installs a
// temporary promise rejection hook on the borrowed isolate.
#include <node.h>
#include "host.h"
#include <stdexcept>

namespace {
using namespace v8;
Local<String> S(Isolate* isolate, const char* s) {
  return String::NewFromUtf8(isolate, s).ToLocalChecked();
}
Local<Value> Get(Local<Context> ctx, Local<Object> object, const char* key) {
  return object->Get(ctx, S(ctx->GetIsolate(), key)).ToLocalChecked();
}
std::string Text(Isolate* isolate, Local<Value> value) {
  String::Utf8Value text(isolate, value);
  return *text ? std::string(*text, text.length()) : "";
}
void Run(const FunctionCallbackInfo<Value>& args) {
  auto* isolate = args.GetIsolate();
  HandleScope scope(isolate);
  auto context = isolate->GetCurrentContext();
  if (args.Length() != 1 || !args[0]->IsString()) {
    isolate->ThrowException(Exception::TypeError(S(isolate, "expected JSON string")));
    return;
  }
  Local<Value> decoded;
  if (!JSON::Parse(context, args[0].As<String>()).ToLocal(&decoded) || !decoded->IsObject()) return;
  auto config = decoded.As<Object>();
  zero::Options options;
  auto profile = Get(context, config, "profile");
  if (profile->IsString()) options.profile = Text(isolate, profile);
  options.virtual_time = Get(context, config, "virtual_time")->IsTrue();
  for (auto item : {std::pair<const char*, std::uint32_t*>{"timeout_ms", &options.timeout_ms},
       {"max_tasks", &options.max_tasks}, {"max_pending", &options.max_pending}}) {
    auto value = Get(context, config, item.first);
    if (value->IsUint32()) *item.second = value.As<Uint32>()->Value();
  }
  auto hz = Get(context, config, "frame_hz");
  if (hz->IsNumber()) options.frame_hz = hz.As<Number>()->Value();
  auto input = Get(context, config, "scripts");
  if (!input->IsArray()) {
    isolate->ThrowException(Exception::TypeError(S(isolate, "scripts array required")));
    return;
  }
  std::vector<zero::Script> scripts;
  auto array = input.As<Array>();
  for (unsigned i = 0; i < array->Length(); ++i) {
    auto value = array->Get(context, i).ToLocalChecked();
    if (!value->IsObject()) return;
    auto script = value.As<Object>();
    scripts.push_back({Text(isolate, Get(context, script, "name")),
                       Text(isolate, Get(context, script, "source"))});
  }
  auto report = zero::Run(isolate, scripts, options);
  const auto json = report.Json(options);
  args.GetReturnValue().Set(String::NewFromUtf8(isolate, json.c_str(), NewStringType::kNormal,
                                             static_cast<int>(json.size())).ToLocalChecked());
}
void Init(Local<Object> exports) { NODE_SET_METHOD(exports, "run", Run); }
NODE_MODULE(NODE_GYP_MODULE_NAME, Init)
}  // namespace
