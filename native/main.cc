#include "host.h"
#include "platform.h"
#ifdef _WIN32
#include <windows.h>
#endif
#include <libplatform/libplatform.h>
#include <fstream>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
void Usage() {
  std::cout << "krunker-zero: browserless, headless JavaScript dependency probe\n"
    "Usage: zero [options] script.js [more scripts, in execution order]\n"
    "  --profile bare|core|graphics  Default: bare; graphics requires opt-in build\n"
    "  --window            Enable optional native Win32 fixture window APIs\n"
    "  --swap-interval 0|1 Window presentation interval (default: 1)\n"
    "  --angle-backend d3d11|warp  Windows graphics device (default: d3d11)\n"
    "  --engine-info       Report compile-time engine features as JSON\n"
    "  --virtual-time      Advance a synthetic clock; NOT a performance benchmark\n"
    "  --timeout-ms N      Wall-clock budget, 1..60000 (default 2000)\n"
    "  --max-tasks N       Callback budget (default 10000)\n"
    "  --max-pending N     Pending callback cap (default 4096)\n"
    "  --frame-hz N        Headless animation cadence, 1..1000 (default 60)\n"
    "  --memory-mb N       V8 old-generation target, 16..4096 (default 256)\n"
    "JSON report goes to stdout. Guest code receives no file/network API.\n";
}
unsigned Number(const std::string& value) {
  if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
    throw std::invalid_argument("expected a positive integer");
  const auto number = std::stoull(value);
  if (number > std::numeric_limits<unsigned>::max()) throw std::out_of_range("integer too large");
  return static_cast<unsigned>(number);
}
zero::Script Load(const std::string& path) {
  std::ifstream file(zero::platform::PathFromUtf8(path), std::ios::binary | std::ios::ate);
  if (!file) throw std::runtime_error("cannot open input: " + path);
  const auto size = file.tellg();
  if (size < 0 || size > 16 * 1024 * 1024) throw std::runtime_error("invalid input size: " + path);
  std::string source(static_cast<std::size_t>(size), '\0');
  file.seekg(0);
  if (!file.read(source.data(), size)) throw std::runtime_error("cannot read input: " + path);
  return {path, std::move(source)};
}
}  // namespace
int RunMain(int argc, char** argv) {
  zero::Options options;
  unsigned memory_mb = 256;
  std::vector<zero::Script> scripts;
  try {
    bool positional = false;
    for (int i = 1; i < argc; ++i) {
      std::string arg = argv[i];
      if (!positional && arg == "--") { positional = true; continue; }
      if (!positional && (arg == "--help" || arg == "-h")) { Usage(); return 0; }
      if (!positional && arg == "--engine-info") {
        std::cout << "{\"engine\":\"V8\",\"version\":" << zero::JsonString(v8::V8::GetVersion())
                  << ",\"host\":\"standalone\",\"sandbox\":"
#ifdef V8_ENABLE_SANDBOX
                  << "true"
#else
                  << "false"
#endif
                  << ",\"intl\":"
#ifdef V8_INTL_SUPPORT
                  << "true"
#else
                  << "false"
#endif
                  << ",\"pointer_compression\":"
#ifdef V8_COMPRESS_POINTERS
                  << "true"
#else
                  << "false"
#endif
                  << ",\"graphics_compiled\":"
#ifdef ZERO_ENABLE_GRAPHICS
                  << "true"
#else
                  << "false"
#endif
                  << ",\"platform\":"
#ifdef _WIN32
                  << "\"windows-x64\""
#else
                  << "\"linux\""
#endif
                  << "}\n";
        return 0;
      }
      if (!positional && arg == "--window") { options.window = true; continue; }
      if (!positional && arg == "--virtual-time") { options.virtual_time = true; continue; }
      if (!positional && arg.rfind("--", 0) == 0) {
        if (i + 1 >= argc) throw std::invalid_argument("missing value: " + arg);
        std::string value = argv[++i];
        if (arg == "--profile") options.profile = value;
        else if (arg == "--swap-interval") options.swap_interval = Number(value);
        else if (arg == "--angle-backend") options.angle_backend = value;
        else if (arg == "--timeout-ms") options.timeout_ms = Number(value);
        else if (arg == "--max-tasks") options.max_tasks = Number(value);
        else if (arg == "--max-pending") options.max_pending = Number(value);
        else if (arg == "--memory-mb") memory_mb = Number(value);
        else if (arg == "--frame-hz") {
          std::size_t used = 0;
          options.frame_hz = std::stod(value, &used);
          if (used != value.size()) throw std::invalid_argument("invalid frame rate");
        } else throw std::invalid_argument("unknown option: " + arg);
      } else scripts.push_back(Load(arg));
    }
    if (scripts.empty()) { Usage(); return 64; }
    if (memory_mb < 16 || memory_mb > 4096) throw std::invalid_argument("memory-mb outside 16..4096");
  } catch (const std::exception& error) {
    std::cerr << error.what() << '\n';
    return 64;
  }
  v8::V8::InitializeICUDefaultLocation(argv[0]);
  v8::V8::InitializeExternalStartupData(argv[0]);
  auto platform = v8::platform::NewDefaultPlatform();
  v8::V8::InitializePlatform(platform.get());
  if (!v8::V8::Initialize()) { std::cerr << "V8 initialization failed\n"; return 70; }
  auto allocator = std::unique_ptr<v8::ArrayBuffer::Allocator>(v8::ArrayBuffer::Allocator::NewDefaultAllocator());
  v8::Isolate::CreateParams params;
  params.array_buffer_allocator = allocator.get();
  params.constraints.set_max_old_generation_size_in_bytes(static_cast<std::size_t>(memory_mb) * 1024 * 1024);
  auto* isolate = v8::Isolate::New(params);
  int status;
  {
    v8::Isolate::Scope entered(isolate);
    auto report = zero::Run(isolate, scripts, options, [&] {
      return v8::platform::PumpMessageLoop(platform.get(), isolate);
    });
    std::cout << report.Json(options) << '\n';
    status = report.exit_code;
  }
  isolate->Dispose();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  return status;
}

#ifdef _WIN32
int wmain(int argc, wchar_t** argv) {
  // Avoid modal loader/crash dialogs in unattended local tests.
  SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
  if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_APPLICATION_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32)) {
    std::cerr << "Cannot restrict DLL search paths: " << GetLastError() << '\n';
    return 70;
  }
  try {
    std::vector<std::string> text;
    text.reserve(argc);
    for (int i = 0; i < argc; ++i) text.push_back(zero::platform::PathToUtf8(std::filesystem::path(argv[i])));
    std::vector<char*> args;
    for (auto& value : text) args.push_back(value.data());
    return RunMain(argc, args.data());
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 70; }
}
#else
int main(int argc, char** argv) { return RunMain(argc, argv); }
#endif
