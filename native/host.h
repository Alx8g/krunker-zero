#pragma once
#include <cstdint>
#include <string>
#include <vector>
#include <v8.h>

namespace zero {
struct Script { std::string name, source; };
struct Options {
  std::string profile = "bare";
  bool virtual_time = false;
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
  std::uint64_t callbacks = 0, checkpoints = 0;
  std::size_t pending_tasks = 0, logs_dropped = 0;
  double elapsed_ms = 0, clock_ms = 0;
  std::vector<Log> logs;
  std::string Json(const Options& options) const;
};
// The caller owns platform/allocator/isolate lifecycle. Guest code runs in a
// fresh Context and a private microtask queue; no caller globals are copied.
Report Run(v8::Isolate* isolate, const std::vector<Script>& scripts, const Options& options);
std::string JsonString(const std::string& text);
}  // namespace zero
