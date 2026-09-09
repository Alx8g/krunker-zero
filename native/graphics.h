#pragma once
#include <memory>
#include <string>
#include <v8.h>
namespace zero {
struct Options;
// Optional experimental graphics backend; no DOM or networking; optional explicit Win32 fixture window.
// Owns every native context/resource for one Run. Never outlives the isolate.
class Graphics {
 public:
  explicit Graphics(v8::Isolate* isolate, const Options& options);
  void PumpEvents();
  bool WindowClosed() const;
  ~Graphics();
  void Bind(v8::Local<v8::Context> context);
  std::string ReportJson() const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
