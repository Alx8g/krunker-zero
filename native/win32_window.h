#pragma once
#include <cstddef>
#include <memory>
#include <vector>

namespace zero {
struct WindowEvent {
  const char* type;
  int x = 0, y = 0, code = 0;
  bool repeat = false;
};
// Optional Win32 fixture surface. No DOM, global input hooks, or background
// input collection. All operations and message dispatch run on the V8 thread.
class Win32Window {
 public:
  Win32Window(int width, int height);
  ~Win32Window();
  Win32Window(const Win32Window&) = delete;
  Win32Window& operator=(const Win32Window&) = delete;
  void* Handle() const;
  void Pump();
  void Close();
  bool Closed() const;
  bool Minimized() const;
  bool CapturePointer(bool enable);
  std::vector<WindowEvent> DrainEvents();
  std::size_t DroppedEvents() const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}  // namespace zero
