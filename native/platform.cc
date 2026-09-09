#include "platform.h"
#include <cstring>
#include <stdexcept>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace zero::platform {
std::filesystem::path PathFromUtf8(std::string_view text) {
  return std::filesystem::u8path(text.begin(), text.end());
}
std::string PathToUtf8(const std::filesystem::path& path) {
  const auto text = path.u8string();
  return {reinterpret_cast<const char*>(text.data()), text.size()};
}
std::filesystem::path ExecutableDirectory() {
#ifdef _WIN32
  for (DWORD capacity = 512; capacity <= 32768; capacity *= 2) {
    std::vector<wchar_t> text(capacity);
    const DWORD size = GetModuleFileNameW(nullptr, text.data(), capacity);
    if (!size) throw std::runtime_error("GetModuleFileNameW failed: " + std::to_string(GetLastError()));
    if (size < capacity) return std::filesystem::path(std::wstring(text.data(), size)).parent_path();
  }
  throw std::runtime_error("Executable path exceeds Windows path limit");
#elif defined(__linux__)
  return std::filesystem::read_symlink("/proc/self/exe").parent_path();
#else
#error "ExecutableDirectory has not been implemented on this platform"
#endif
}
void SharedLibrary::Open(const std::filesystem::path& file) {
  if (handle_) throw std::logic_error("library already loaded");
  if (!file.is_absolute()) throw std::invalid_argument("library path must be absolute");
#ifdef _WIN32
  handle_ = reinterpret_cast<void*>(LoadLibraryExW(file.c_str(), nullptr,
      LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32));
  if (!handle_) throw std::runtime_error("Cannot load " + PathToUtf8(file) +
      " (Win32 error " + std::to_string(GetLastError()) + "); no graphics fallback");
#else
  handle_ = dlopen(file.c_str(), RTLD_NOW | RTLD_LOCAL);
  if (!handle_) {
    const char* error = dlerror();
    throw std::runtime_error("Cannot load " + PathToUtf8(file) + ": " + (error ? error : "unknown loader error"));
  }
#endif
}
void SharedLibrary::OpenSystem(const char* name) {
#ifdef _WIN32
  (void)name;
  throw std::logic_error("Windows libraries must be loaded from an explicit absolute path");
#else
  if (handle_) throw std::logic_error("library already loaded");
  handle_ = dlopen(name, RTLD_NOW | RTLD_LOCAL);
  if (!handle_) throw std::runtime_error(std::string(name) + " unavailable; no graphics fallback");
#endif
}
SharedLibrary::Entry SharedLibrary::Find(const char* name) const noexcept {
  if (!handle_) return nullptr;
#ifdef _WIN32
  const auto value = GetProcAddress(reinterpret_cast<HMODULE>(handle_), name);
#else
  const auto value = dlsym(handle_, name);
#endif
  Entry entry = nullptr;
  static_assert(sizeof(entry) == sizeof(value));
  std::memcpy(&entry, &value, sizeof(entry));
  return entry;
}
SharedLibrary::~SharedLibrary() {
  if (!handle_) return;
#ifdef _WIN32
  FreeLibrary(reinterpret_cast<HMODULE>(handle_));
#else
  dlclose(handle_);
#endif
}
}  // namespace zero::platform
