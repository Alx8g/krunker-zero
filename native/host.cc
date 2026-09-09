#include "host.h"
#include "task_queue.h"
#include "core_prelude.h"
#ifdef ZERO_ENABLE_GRAPHICS
#include "graphics.h"
#include "graphics_prelude.h"
#endif
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <iomanip>
#include <limits>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <thread>
#include <type_traits>
#include <utility>

namespace zero {
namespace {
using Clock = std::chrono::steady_clock;
using namespace v8;
struct Rejection { Global<Promise> promise; Global<Value> reason; };
struct State {
  Isolate* isolate;
  const Options& options;
  Report& report;
  TaskQueue queue;
  std::map<TaskId, Global<Function>> callbacks;
  std::vector<Rejection> rejections;
  std::vector<Global<Promise>> promises;
  Clock::time_point start = Clock::now();
  double virtual_now = 0;
  State(Isolate* i, const Options& o, Report& r)
      : isolate(i), options(o), report(r), queue(o.frame_hz, o.max_pending) {}
  double Now() const {
    return options.virtual_time ? virtual_now :
      std::chrono::duration<double, std::milli>(Clock::now() - start).count();
  }
};
thread_local State* active_state = nullptr;

// Join before destroying the isolate or cancelling a termination request.
class Watchdog {
 public:
  Watchdog(Isolate* isolate, unsigned ms) : thread_([this, isolate, ms] {
    std::unique_lock<std::mutex> lock(mutex_);
    if (!cv_.wait_for(lock, std::chrono::milliseconds(ms), [this] { return stopped_; })) {
      expired_.store(true);
      isolate->TerminateExecution();
    }
  }) {}
  void Stop() {
    { std::lock_guard<std::mutex> lock(mutex_); stopped_ = true; }
    cv_.notify_one();
    if (thread_.joinable()) thread_.join();
  }
  bool Expired() const { return expired_.load(); }
  ~Watchdog() { Stop(); }
 private:
  std::mutex mutex_;
  std::condition_variable cv_;
  bool stopped_ = false;
  std::atomic<bool> expired_{false};
  std::thread thread_;
};
Local<String> Str(Isolate* isolate, const std::string& s) {
  return String::NewFromUtf8(isolate, s.data(), NewStringType::kNormal,
                            static_cast<int>(s.size())).ToLocalChecked();
}
std::string Text(Isolate* isolate, Local<Value> value, std::size_t limit = 16384) {
  String::Utf8Value text(isolate, value);
  if (!*text) return "<unavailable>";
  const std::size_t length = std::min(limit, static_cast<std::size_t>(text.length()));
  std::string result(*text, length);
  // Avoid truncating inside a UTF-8 codepoint.
  if (length < static_cast<std::size_t>(text.length())) {
    std::size_t cut = length;
    while (cut && (static_cast<unsigned char>((*text)[cut]) & 0xc0) == 0x80) --cut;
    result.assign(*text, cut);
    result += "...[truncated]";
  }
  return result;
}
State& Data(const FunctionCallbackInfo<Value>& args) {
  return *static_cast<State*>(args.Data().As<External>()->Value());
}
void NativeNow(const FunctionCallbackInfo<Value>& args) {
  args.GetReturnValue().Set(Data(args).Now());
}
void NativeLog(const FunctionCallbackInfo<Value>& args) {
  auto& s = Data(args);
  if (args.Length() != 2 || !args[0]->IsString() || !args[1]->IsString()) return;
  if (s.report.logs.size() >= 512) { ++s.report.logs_dropped; return; }
  s.report.logs.push_back({Text(args.GetIsolate(), args[0], 16),
                           Text(args.GetIsolate(), args[1], 4096)});
}
void NativeSchedule(const FunctionCallbackInfo<Value>& args) {
  auto& s = Data(args);
  auto isolate = args.GetIsolate();
  if (args.Length() != 4 || !args[0]->IsFunction() || !args[1]->IsNumber()) {
    isolate->ThrowException(Exception::TypeError(Str(isolate, "invalid task")));
    return;
  }
  try {
    const auto id = s.queue.Add(s.Now(), args[1].As<Number>()->Value(),
                               args[2]->IsTrue(), args[3]->IsTrue());
    s.callbacks.emplace(id, Global<Function>(isolate, args[0].As<Function>()));
    args.GetReturnValue().Set(static_cast<double>(id));
  } catch (const std::exception& error) {
    isolate->ThrowException(Exception::RangeError(Str(isolate, error.what())));
  }
}
void NativeCancel(const FunctionCallbackInfo<Value>& args) {
  auto& s = Data(args);
  if (!args.Length() || !args[0]->IsNumber()) return;
  const double number = args[0].As<Number>()->Value();
  if (!std::isfinite(number) || number <= 0 || number >= 9007199254740991.0) return;
  const auto id = static_cast<TaskId>(number);
  s.queue.Cancel(id);
  s.callbacks.erase(id);
}
// A resolve hook fires before settlement and can adopt a still-pending promise.
// Observe weak handles and inspect actual state after microtask checkpoints.
// Do not mutate Promise/WebAssembly constructors or expose new guest globals.
std::size_t PendingPromises(State& s);
void ObservePromise(PromiseHookType type, Local<Promise> promise, Local<Value>) {
  if (!active_state || type != PromiseHookType::kInit) return;
  auto& s = *active_state;
  constexpr std::size_t kObservationLimit = 65536;
  if (s.report.promise_observation_overflow) return;
  if (s.promises.size() >= kObservationLimit) PendingPromises(s);
  if (s.promises.size() >= kObservationLimit) {
    s.report.promise_observation_overflow = true;
    return;
  }
  Global<Promise> observed(s.isolate, promise);
  observed.SetWeak();
  s.promises.push_back(std::move(observed));
}
std::size_t PendingPromises(State& s) {
  HandleScope handles(s.isolate);
  auto& list = s.promises;
  list.erase(std::remove_if(list.begin(), list.end(), [&](const Global<Promise>& p) {
    return p.IsEmpty() || p.Get(s.isolate)->State() != Promise::kPending;
  }), list.end());
  s.report.pending_promises = list.size();
  return list.size();
}
void Reject(PromiseRejectMessage event) {
  if (!active_state) return;
  auto& s = *active_state;
  if (event.GetEvent() == kPromiseRejectWithNoHandler) {
    s.rejections.push_back({Global<Promise>(s.isolate, event.GetPromise()),
                            Global<Value>(s.isolate, event.GetValue())});
  } else if (event.GetEvent() == kPromiseHandlerAddedAfterReject) {
    auto& pending = s.rejections;
    pending.erase(std::remove_if(pending.begin(), pending.end(), [&](const Rejection& r) {
      return r.promise.Get(s.isolate) == event.GetPromise();
    }), pending.end());
  }
}
void Failure(State& s, Local<Context> context, TryCatch& caught, const char* phase) {
  auto& report = s.report;
  report.phase = phase;
  if (s.isolate->IsExecutionTerminating() || caught.HasTerminated()) {
    report.status = "execution_timeout";
    report.message = "wall-clock execution budget exhausted";
    report.exit_code = 3;
    return;
  }
  report.status = "script_exception";
  report.exit_code = 2;
  auto message = caught.Message();
  report.message = message.IsEmpty() ? "JavaScript exception" : Text(s.isolate, message->Get());
  if (!message.IsEmpty()) {
    report.line = message->GetLineNumber(context).FromMaybe(0);
    report.column = message->GetStartColumn(context).FromMaybe(-1) + 1;
    report.source = Text(s.isolate, message->GetScriptResourceName());
  }
  Local<Value> stack;
  if (caught.StackTrace(context).ToLocal(&stack) && stack->IsString())
    report.stack = Text(s.isolate, stack);
  // Only classify the exact V8 missing-identifier message; never infer an API
  // path from an ambiguous TypeError. Caught errors inside guest code are not
  // visible here, and diagnostics do not insert placeholder globals.
  const std::string prefix = "Uncaught ReferenceError: ", suffix = " is not defined";
  if (report.message.compare(0, prefix.size(), prefix) == 0 &&
      report.message.size() >= prefix.size() + suffix.size() &&
      report.message.compare(report.message.size() - suffix.size(), suffix.size(), suffix) == 0) {
    const auto name = report.message.substr(prefix.size(),
      report.message.size() - prefix.size() - suffix.size());
    if (name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$") == std::string::npos) {
      report.missing_global = name;
      report.status = "missing_global";
    }
  }
}
// V8 changed ScriptOrigin's constructor between the tested 12.x and 13.x
// engines. Select from the installed header API rather than guessing a version.
template <class Origin = ScriptOrigin>
Origin MakeOrigin(Isolate* isolate, Local<String> name) {
  if constexpr (std::is_constructible_v<Origin, Isolate*, Local<String>>)
    return Origin(isolate, name);
  else
    return Origin(name);
}
bool Evaluate(State& s, Local<Context> context, const Script& input, const char* phase) {
  HandleScope handles(s.isolate);
  TryCatch caught(s.isolate);
  auto origin = MakeOrigin(s.isolate, Str(s.isolate, input.name));
  Local<v8::Script> script;
  Local<Value> result;
  if (!v8::Script::Compile(context, Str(s.isolate, input.source), &origin).ToLocal(&script) ||
      !script->Run(context).ToLocal(&result)) {
    Failure(s, context, caught, phase);
    return false;
  }
  return true;
}
bool Checkpoint(State& s, Local<Context> context, MicrotaskQueue* microtasks) {
  TryCatch caught(s.isolate);
  microtasks->PerformCheckpoint(s.isolate);
  ++s.report.checkpoints;
  if (s.isolate->IsExecutionTerminating() || caught.HasCaught()) {
    Failure(s, context, caught, "microtask");
    return false;
  }
  return true;
}
bool Unhandled(State& s, Local<Context> context) {
  if (s.rejections.empty()) return false;
  auto& r = s.report;
  r.status = "unhandled_rejection";
  r.phase = "microtask";
  r.exit_code = 2;
  TryCatch caught(s.isolate);
  r.message = Text(s.isolate, s.rejections.front().reason.Get(s.isolate));
  if (caught.HasTerminated() || s.isolate->IsExecutionTerminating())
    Failure(s, context, caught, "rejection-reporting");
  return true;
}
void Bind(State& s, Local<Context> context) {
  auto object = Object::New(s.isolate);
  for (const auto& item : std::vector<std::pair<const char*, FunctionCallback>>{
      {"now", NativeNow}, {"log", NativeLog}, {"schedule", NativeSchedule}, {"cancel", NativeCancel}}) {
    object->Set(context, Str(s.isolate, item.first),
      Function::New(context, item.second, External::New(s.isolate, &s)).ToLocalChecked()).Check();
  }
  context->Global()->Set(context, Str(s.isolate, "__zeroNative"), object).Check();
}
}  // namespace

std::string JsonString(const std::string& text) {
  std::ostringstream out;
  out << '"';
  for (unsigned char c : text) {
    switch (c) {
      case '"': out << "\\\""; break;
      case '\\': out << "\\\\"; break;
      case '\b': out << "\\b"; break;
      case '\f': out << "\\f"; break;
      case '\n': out << "\\n"; break;
      case '\r': out << "\\r"; break;
      case '\t': out << "\\t"; break;
      default:
        if (c < 32) out << "\\u" << std::hex << std::setw(4) << std::setfill('0')
                        << static_cast<int>(c) << std::dec;
        else out << c;
    }
  }
  return out.str() + '"';
}
std::string Report::Json(const Options& options) const {
  std::ostringstream out;
  out << std::setprecision(12)
      << "{\"schema\":1,\"engine\":\"V8\",\"engine_version\":" << JsonString(v8::V8::GetVersion())
      << ",\"profile\":" << JsonString(options.profile)
      << ",\"mode\":\"headless\",\"virtual_time\":" << (options.virtual_time ? "true" : "false")
      << ",\"status\":" << JsonString(status) << ",\"exit_code\":" << exit_code
      << ",\"phase\":" << JsonString(phase) << ",\"message\":" << JsonString(message)
      << ",\"stack\":" << JsonString(stack) << ",\"missing_global\":" << JsonString(missing_global)
      << ",\"source\":" << JsonString(source) << ",\"line\":" << line << ",\"column\":" << column
      << ",\"callbacks\":" << callbacks << ",\"microtask_checkpoints\":" << checkpoints
      << ",\"engine_tasks\":" << engine_tasks << ",\"pending_promises\":" << pending_promises
      << ",\"promise_observation_overflow\":" << (promise_observation_overflow ? "true" : "false")
      << ",\"pending_tasks\":" << pending_tasks << ",\"elapsed_ms\":" << elapsed_ms
      << ",\"clock_ms\":" << clock_ms << ",\"logs_dropped\":" << logs_dropped << ",\"logs\":[";
  for (std::size_t i = 0; i < logs.size(); ++i) {
    if (i) out << ',';
    out << "{\"level\":" << JsonString(logs[i].level) << ",\"text\":" << JsonString(logs[i].text) << '}';
  }
  return out.str() + "]" + (graphics_json.empty() ? "" : ",\"graphics\":" + graphics_json) + "}";
}

Report Run(Isolate* isolate, const std::vector<Script>& scripts, const Options& options,
           const std::function<bool()>& pump_engine) {
  Report report;
  if ((options.profile != "bare" && options.profile != "core"
#ifdef ZERO_ENABLE_GRAPHICS
      && options.profile != "graphics"
#endif
     ) ||
      !options.timeout_ms || options.timeout_ms > 60000 || !options.max_tasks ||
      !options.max_pending || options.max_pending > 100000 ||
      !std::isfinite(options.frame_hz) || options.frame_hz < 1 || options.frame_hz > 1000) {
    report.status = "configuration_error";
    report.message = "invalid run options";
    report.exit_code = 64;
    return report;
  }
  if (options.swap_interval > 1 || (options.window && (options.profile != "graphics" || options.virtual_time
#ifndef _WIN32
      || true
#endif
      ))) {
    report.status = "configuration_error";
    report.message = "window requires Windows graphics, real time, and swap-interval 0 or 1";
    report.exit_code = 64;
    return report;
  }
  if (!options.angle_backend.empty() &&
      (options.profile != "graphics"
#ifdef _WIN32
       || (options.angle_backend != "d3d11" && options.angle_backend != "warp")
#else
       || true
#endif
       )) {
    report.status = "configuration_error";
    report.message = "angle-backend is Windows graphics-only: d3d11 or warp";
    report.exit_code = 64;
    return report;
  }
  HandleScope handles(isolate);
  auto microtasks = MicrotaskQueue::New(isolate, MicrotasksPolicy::kExplicit);
  auto context = Context::New(isolate, nullptr, {}, {}, {}, microtasks.get());
  Context::Scope entered(context);
  // V8 itself installs a debugging console in a fresh context. It is not
  // part of the bare runtime contract and must not become a silent no-op.
  context->Global()->Delete(context, Str(isolate, "console")).Check();
  State state(isolate, options, report);
  active_state = &state;
  isolate->SetPromiseRejectCallback(Reject);
  isolate->SetPromiseHook(ObservePromise);
  Watchdog watchdog(isolate, options.timeout_ms);
  bool ok = true;
#ifdef ZERO_ENABLE_GRAPHICS
  std::unique_ptr<Graphics> graphics;
#endif
  if (options.profile == "core" || options.profile == "graphics") {
    Bind(state, context);
    ok = Evaluate(state, context,
        {"zero:core", reinterpret_cast<const char*>(kCorePrelude)}, "bootstrap");
  }
#ifdef ZERO_ENABLE_GRAPHICS
  if (ok && options.profile == "graphics") {
    graphics = std::make_unique<Graphics>(isolate, options);
    graphics->Bind(context);
    ok = Evaluate(state, context,
        {"zero:graphics", reinterpret_cast<const char*>(kGraphicsPrelude)}, "graphics-bootstrap");
  }
#endif
  if (ok) {
    for (const auto& script : scripts) {
      if (script.source.size() > 16 * 1024 * 1024) {
        report.status = "configuration_error";
        report.message = "script exceeds 16 MiB source limit";
        report.exit_code = 64;
        ok = false;
        break;
      }
      if (!Evaluate(state, context, script, "script") ||
          !Checkpoint(state, context, microtasks.get()) || Unhandled(state, context)) {
        ok = false;
        break;
      }
    }
  }
  while (ok) {
#ifdef ZERO_ENABLE_GRAPHICS
    if (graphics) {
      graphics->PumpEvents();
      if (graphics->WindowClosed()) {
        report.status = "window_closed";
        report.message = "native window closed; remaining callbacks were not executed";
        break;
      }
    }
#endif
    const auto pending = PendingPromises(state);
    if (report.promise_observation_overflow) {
      report.status = "promise_observation_limit";
      report.message = "promise observation cap exceeded; async completion is unknown";
      report.exit_code = 3;
      break;
    }
    if (watchdog.Expired()) {
      report.status = pending && !state.queue.Size() ? "async_work_timeout" : "execution_timeout";
      report.message = "wall-clock execution budget exhausted";
      report.exit_code = 3;
      break;
    }
    // Nonblocking: an empty foreground queue does not mean background Wasm
    // compilation finished. Pending promises keep this bounded probe alive.
    bool pumped = false;
    if (pump_engine && report.engine_tasks >= options.max_tasks && pending) {
      report.status = "task_budget_exhausted";
      report.message = "engine task budget exhausted; run is incomplete";
      report.exit_code = 3;
      break;
    }
    if (pump_engine && report.engine_tasks < options.max_tasks) {
      TryCatch caught(isolate);
      pumped = pump_engine();
      if (caught.HasCaught() || isolate->IsExecutionTerminating()) {
        Failure(state, context, caught, "engine-task");
        break;
      }
      if (pumped) {
        ++report.engine_tasks;
        if (!Checkpoint(state, context, microtasks.get()) || Unhandled(state, context)) break;

      }
    }
    if (!state.queue.Size()) {
      if (!PendingPromises(state)) {
        if (pumped) continue;
        break;
      }
      if (!pump_engine) {
        report.status = "async_work_pending";
        report.message = "unresolved promises; this adapter cannot pump V8 platform tasks";
        report.exit_code = 3;
        break;
      }
      std::this_thread::sleep_for(std::chrono::milliseconds(1));
      continue;
    }
    const double due = state.queue.NextDue();
    if (options.virtual_time) state.virtual_now = std::max(state.virtual_now, due);
    else if (due > state.Now()) {
      std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(
        std::min(10.0, due - state.Now())));
      continue;
    }
    const double frame_time = state.Now();
    const auto ready = state.queue.Ready(frame_time);
    for (const auto id : ready) {
      if (!state.queue.Contains(id)) continue;
      if (report.callbacks >= options.max_tasks) {
        report.status = "task_budget_exhausted";
        report.message = "callback budget exhausted; run is incomplete";
        report.exit_code = 3;
        ok = false;
        break;
      }
      HandleScope callback_handles(isolate);
      auto callback = state.callbacks.at(id).Get(isolate);
      const auto task = state.queue.Take(id, state.Now());
      if (task.interval_ms == 0) state.callbacks.erase(id);
      TryCatch caught(isolate);
      Local<Value> result;
      Local<Value> argument = Number::New(isolate, frame_time);
      ++report.callbacks;
      if (!callback->Call(context, context->Global(), task.frame ? 1 : 0, &argument).ToLocal(&result)) {
        Failure(state, context, caught, task.frame ? "animation-frame" : "timer");
        ok = false;
        break;
      }
      if (!Checkpoint(state, context, microtasks.get()) || Unhandled(state, context)) {
        ok = false;
        break;
      }
#ifdef ZERO_ENABLE_GRAPHICS
      // A close in one callback must also stop other callbacks in the same batch.
      if (graphics && graphics->WindowClosed()) break;
#endif
    }
  }
  watchdog.Stop();
  if (watchdog.Expired() && report.exit_code == 0) {
    report.status = "execution_timeout";
    report.message = "wall-clock execution budget exhausted";
    report.exit_code = 3;
  }
  // The development harness can now report a terminated run without leaving
  // its enclosing isolate poisoned. Standalone uses the same path.
  // A termination requested while native code is idle can still be queued,
  // without IsExecutionTerminating() becoming true yet. Cancel it as well.
  if (watchdog.Expired() || isolate->IsExecutionTerminating()) isolate->CancelTerminateExecution();
  report.pending_promises = PendingPromises(state);
  isolate->SetPromiseRejectCallback(nullptr);
  isolate->SetPromiseHook(nullptr);
  active_state = nullptr;
#ifdef ZERO_ENABLE_GRAPHICS
  if (graphics) report.graphics_json = graphics->ReportJson();
#endif
  report.pending_tasks = state.queue.Size();
  report.clock_ms = state.Now();
  report.elapsed_ms = std::chrono::duration<double, std::milli>(Clock::now() - state.start).count();
  return report;
}
}  // namespace zero
