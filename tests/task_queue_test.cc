#include "task_queue.h"
#include <cmath>
#include <iostream>
#include <stdexcept>
using namespace zero;
void check(bool condition, const char* reason) {
  if (!condition) throw std::runtime_error(reason);
}
int main() {
  TaskQueue q(60, 4);
  auto later = q.Add(0, 10, false, false);
  auto first = q.Add(0, 0, false, false);
  auto second = q.Add(0, 0, false, false);
  check(q.Ready(0) == std::vector<TaskId>{first, second}, "due time and FIFO");
  q.Take(first, 0);
  q.Cancel(second);
  check(q.NextDue() == 10, "next deadline");
  q.Take(later, 10);
  check(q.Size() == 0, "one-shot removed");
  auto interval = q.Add(0, 0, true, false);
  check(q.NextDue() == 1, "zero interval is bounded");
  check(q.Ready(0).empty(), "future tasks are not ready");
  q.Take(interval, 5);
  check(q.NextDue() == 6, "no interval catch-up storm");
  check(q.Contains(interval), "interval persists under the same ID");
  q.Cancel(interval);
  auto a = q.Add(0, 0, false, true);
  auto b = q.Add(0, 0, false, true);
  auto frame_time = q.NextDue();
  auto batch = q.Ready(frame_time);
  check(batch == std::vector<TaskId>{a, b}, "frame batch");
  q.Take(a, frame_time);
  q.Cancel(b);
  auto nested = q.Add(frame_time, 0, false, true);
  check(q.NextDue() > frame_time && q.Contains(nested), "nested frame deferred");
  check(!q.Cancel(900), "unknown cancel harmless");
  TaskQueue small(60, 1);
  small.Add(0, 0, false, false);
  bool limited = false;
  try { small.Add(0, 0, false, false); } catch (const std::length_error&) { limited = true; }
  check(limited, "pending capacity enforced");
  bool invalid = false;
  try { TaskQueue bad(0, 1); } catch (const std::invalid_argument&) { invalid = true; }
  check(invalid, "invalid frame rate rejected");
  std::cout << "PASS: 12 native scheduler checks\n";
}
