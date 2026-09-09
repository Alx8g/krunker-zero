#pragma once
#include <memory>
#include <string>
#include <v8.h>
namespace zero {
// Optional experimental graphics backend; no DOM, networking or window system.
// Owns every native context/resource for one Run. Never outlives the isolate.
class Graphics {
 public:
  explicit Graphics(v8::Isolate* isolate);
  ~Graphics();
  void Bind(v8::Local<v8::Context> context);
  std::string ReportJson() const;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
