#include "platform.h"
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>

int main() {
  unsigned checks = 0;
  auto check = [&](bool value) { ++checks; if (!value) throw std::runtime_error("platform check failed: " + std::to_string(checks)); };
  try {
    using namespace zero::platform;
    const std::string name = "path with spaces-\xe6\x97\xa5\xe6\x9c\xac\xe8\xaa\x9e-\xf0\x9f\x8e\xae.js";
    check(PathToUtf8(PathFromUtf8(name)) == name);
    const auto directory = ExecutableDirectory();
    check(directory.is_absolute() && std::filesystem::is_directory(directory));
    // Write inside the build tree, never a user's input file.
    const auto file = directory / PathFromUtf8(name);
    { std::ofstream out(file, std::ios::binary); out << "utf8"; check(out.good()); }
    { std::ifstream in(file, std::ios::binary); std::string text; in >> text; check(text == "utf8"); }
    check(std::filesystem::remove(file));
    SharedLibrary missing;
    check(missing.Find("anything") == nullptr);
    try { missing.Open("relative.dll"); check(false); } catch (const std::invalid_argument&) { check(true); }
    try { missing.Open(directory / "zero-fixture-does-not-exist.dll"); check(false); } catch (const std::runtime_error&) { check(true); }
    SharedLibrary library;
#ifdef _WIN32
    library.Open(directory / "zero_platform_fixture.dll");
#else
    library.Open(directory / "libzero_platform_fixture.so");
#endif
    const auto symbol = library.Find("zero_fixture_answer");
    check(symbol != nullptr);
    int (*answer)() = nullptr;
    static_assert(sizeof(answer) == sizeof(symbol));
    std::memcpy(&answer, &symbol, sizeof(answer));
    check(answer() == 42);
    check(library.Find("not_exported") == nullptr);
    try { library.Open(directory / "unused.dll"); check(false); } catch (const std::logic_error&) { check(true); }
    std::cout << checks << " platform checks passed\n";
    return 0;
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
