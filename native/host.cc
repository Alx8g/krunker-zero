#include "host.h"
#include "task_queue.h"
#include "core_prelude.h"
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
bool Evaluate(State& s, Local<Context> context, const Script& input, const char* phase) {
  HandleScope handles(s.isolate);
  TryCatch caught(s.isolate);
  ScriptOrigin origin(s.isolate, Str(s.isolate, input.name));
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
      << ",\"pending_tasks\":" << pending_tasks << ",\"elapsed_ms\":" << elapsed_ms
      << ",\"clock_ms\":" << clock_ms << ",\"logs_dropped\":" << logs_dropped << ",\"logs\":[";
  for (std::size_t i = 0; i < logs.size(); ++i) {
    if (i) out << ',';
    out << "{\"level\":" << JsonString(logs[i].level) << ",\"text\":" << JsonString(logs[i].text) << '}';
  }
  return out.str() + "]}";
}

Report Run(Isolate* isolate, const std::vector<Script>& scripts, const Options& options) {
  Report report;
  if ((options.profile != "bare" && options.profile != "core") ||
      !options.timeout_ms || options.timeout_ms > 60000 || !options.max_tasks ||
      !options.max_pending || options.max_pending > 100000 ||
      !std::isfinite(options.frame_hz) || options.frame_hz < 1 || options.frame_hz > 1000) {
    report.status = "configuration_error";
    report.message = "invalid run options";
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
  Watchdog watchdog(isolate, options.timeout_ms);
  bool ok = true;
  if (options.profile == "core") {
    Bind(state, context);
    ok = Evaluate(state, context,
        {"zero:core", reinterpret_cast<const char*>(kCorePrelude)}, "bootstrap");
  }
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
  while (ok && state.queue.Size()) {
    if (watchdog.Expired()) {
      report.status = "execution_timeout";
      report.message = "wall-clock execution budget exhausted";
      report.exit_code = 3;
      break;
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
  isolate->SetPromiseRejectCallback(nullptr);
  active_state = nullptr;
  report.pending_tasks = state.queue.Size();
  report.clock_ms = state.Now();
  report.elapsed_ms = std::chrono::duration<double, std::milli>(Clock::now() - state.start).count();
  return report;
}
}  // namespace zero
