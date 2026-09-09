#include "task_queue.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace zero {
TaskQueue::TaskQueue(double hz, std::size_t capacity)
    : frame_ms_(1000.0 / hz), capacity_(capacity) {
  if (!std::isfinite(hz) || hz < 1 || hz > 1000 || !capacity)
    throw std::invalid_argument("invalid scheduler configuration");
}
TaskId TaskQueue::Add(double now, double delay, bool repeating, bool frame) {
  if (!std::isfinite(now) || now < 0 || !std::isfinite(delay) || delay < 0)
    throw std::invalid_argument("invalid task time");
  if (tasks_.size() >= capacity_) throw std::length_error("pending task limit");
  if (next_id_ >= 9007199254740991ULL) throw std::overflow_error("task ID limit");
  const double interval = repeating ? std::max(1.0, delay) : 0;
  double due = frame ? (std::floor(now / frame_ms_) + 1) * frame_ms_
                     : now + (repeating ? interval : delay);
  // Floating-point precision must not schedule a frame in its own batch.
  if (frame && due <= now) due = now + frame_ms_;
  Task task{next_id_++, due, interval, frame};
  tasks_.emplace(task.id, task);
  return task.id;
}
bool TaskQueue::Cancel(TaskId id) { return tasks_.erase(id) != 0; }
bool TaskQueue::Contains(TaskId id) const { return tasks_.count(id) != 0; }
double TaskQueue::NextDue() const {
  double result = std::numeric_limits<double>::infinity();
  for (const auto& pair : tasks_) result = std::min(result, pair.second.due_ms);
  return result;
}
std::vector<TaskId> TaskQueue::Ready(double now) const {
  std::vector<Task> ready;
  for (const auto& pair : tasks_)
    if (pair.second.due_ms <= now) ready.push_back(pair.second);
  std::sort(ready.begin(), ready.end(), [](const Task& a, const Task& b) {
    if (a.due_ms != b.due_ms) return a.due_ms < b.due_ms;
    return a.id < b.id;
  });
  std::vector<TaskId> ids;
  for (const auto& task : ready) ids.push_back(task.id);
  return ids;
}
Task TaskQueue::Take(TaskId id, double now) {
  auto it = tasks_.find(id);
  if (it == tasks_.end()) throw std::out_of_range("cancelled task");
  Task result = it->second;
  if (result.interval_ms > 0) it->second.due_ms = now + result.interval_ms;
  else tasks_.erase(it);
  return result;
}
}  // namespace zero
