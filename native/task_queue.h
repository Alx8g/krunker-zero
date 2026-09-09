#pragma once
#include <cstdint>
#include <map>
#include <vector>

namespace zero {
using TaskId = std::uint64_t;
struct Task {
  TaskId id;
  double due_ms;
  double interval_ms;
  bool frame;
};

// Scheduling only. No engine, window system, browser, or OS dependencies.
class TaskQueue {
 public:
  explicit TaskQueue(double frame_hz = 60.0, std::size_t capacity = 4096);
  TaskId Add(double now_ms, double delay_ms, bool repeating, bool frame);
  bool Cancel(TaskId id);
  bool Contains(TaskId id) const;
  std::size_t Size() const { return tasks_.size(); }
  double NextDue() const;
  std::vector<TaskId> Ready(double now_ms) const;
  // Called BEFORE invoking JS, so clearInterval from its own callback works.
  Task Take(TaskId id, double now_ms);
 private:
  std::map<TaskId, Task> tasks_;
  TaskId next_id_ = 1;
  double frame_ms_;
  std::size_t capacity_;
};
}  // namespace zero
