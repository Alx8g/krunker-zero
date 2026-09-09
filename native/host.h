#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
#include <v8.h>

namespace zero {
struct Script { std::string name, source; };
struct Options {
  std::string profile = "bare";
  bool virtual_time = false;
  bool window = false;
  unsigned swap_interval = 1;
  std::string angle_backend;  // Windows graphics: empty/d3d11 or explicit warp.
  double frame_hz = 60;
  std::uint32_t timeout_ms = 2000;
  std::uint32_t max_tasks = 10000;
  std::uint32_t max_pending = 4096;
};
struct Log { std::string level, text; };
struct Report {
  std::string status = "completed";
  std::string phase, message, stack, missing_global, source;
  int line = 0, column = 0;
  int exit_code = 0;
  std::uint64_t callbacks = 0, checkpoints = 0, engine_tasks = 0;
  std::size_t pending_promises = 0;
  bool promise_observation_overflow = false;
  std::size_t pending_tasks = 0, logs_dropped = 0;
  double elapsed_ms = 0, clock_ms = 0;
  std::vector<Log> logs;
  std::string graphics_json;
  std::string Json(const Options& options) const;
};
// The caller owns platform/allocator/isolate lifecycle. Guest code runs in a
// fresh Context and a private microtask queue; no caller globals are copied.
// The standalone caller supplies a nonblocking pump for its V8 default platform.
// A development adapter without a pump reports unresolved async work instead of
// claiming it completed. The callback must run only on the isolate's thread.
Report Run(v8::Isolate* isolate, const std::vector<Script>& scripts, const Options& options,
           const std::function<bool()>& pump_engine = {});
std::string JsonString(const std::string& text);
}  // namespace zero
