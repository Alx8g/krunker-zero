#pragma once
#include <filesystem>
#include <string>
#include <string_view>

namespace zero::platform {
// CLI and reports use UTF-8; Windows filesystem operations use UTF-16 internally.
std::filesystem::path PathFromUtf8(std::string_view text);
std::string PathToUtf8(const std::filesystem::path& path);
std::filesystem::path ExecutableDirectory();

class SharedLibrary {
 public:
  using Entry = void (*)();
  SharedLibrary() = default;
  ~SharedLibrary();
  SharedLibrary(const SharedLibrary&) = delete;
  SharedLibrary& operator=(const SharedLibrary&) = delete;
  // Absolute file only. On Windows, dependencies may come from the DLL's own
  // directory or System32, never the working directory or PATH.
  void Open(const std::filesystem::path& absolute_file);
  // Uses the normal ELF loader on Linux. Not a Windows PATH search facility.
  void OpenSystem(const char* name);
  Entry Find(const char* name) const noexcept;
 private:
  void* handle_ = nullptr;
};
}  // namespace zero::platform
