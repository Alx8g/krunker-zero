#include "win32_window.h"
#include <windows.h>
#include <windowsx.h>
#include <stdexcept>
#include <string>
#include <utility>

namespace zero {
struct Win32Window::Impl {
  HWND hwnd = nullptr;
  bool closed = false, minimized = false, captured = false;
  std::size_t dropped = 0;
  std::vector<WindowEvent> events;
  static constexpr std::size_t kMaxEvents = 2048;
  void Add(WindowEvent event) noexcept {
    // Never let an allocation exception cross a Windows callback ABI boundary.
    if (events.size() == kMaxEvents) { ++dropped; return; }
    events.push_back(event); // Capacity reserved before CreateWindowExW.
  }
  void Release() noexcept {
    if (!captured) return;
    captured = false;
    ClipCursor(nullptr);
    if (GetCapture() == hwnd) ReleaseCapture();
    SetCursor(LoadCursorW(nullptr, IDC_ARROW));
  }
  static LRESULT CALLBACK Procedure(HWND hwnd, UINT message, WPARAM w, LPARAM l) {
    auto* self = reinterpret_cast<Impl*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    if (message == WM_NCCREATE) {
      self = static_cast<Impl*>(reinterpret_cast<CREATESTRUCTW*>(l)->lpCreateParams);
      self->hwnd = hwnd;
      SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
    }
    if (!self) return DefWindowProcW(hwnd, message, w, l);
    switch (message) {
      case WM_GETMINMAXINFO:
        // Fixture buffers may be smaller than the system's caption minimum.
        reinterpret_cast<MINMAXINFO*>(l)->ptMinTrackSize = {1, 1};
        return 0;
      case WM_CLOSE:
        self->closed = true; self->Release(); self->Add({"close"});
        return 0; // EGL destroys its surface before the HWND is destroyed.
      case WM_DESTROY: self->closed = true; self->Release(); return 0;
      case WM_KILLFOCUS: self->Release(); self->Add({"blur"}); break;
      case WM_SETFOCUS: self->Add({"focus"}); break;
      case WM_SIZE:
        self->minimized = w == SIZE_MINIMIZED;
        if (self->minimized) self->Release();
        break;
      case WM_MOVE: case WM_CANCELMODE: case WM_ENTERMENULOOP: case WM_ENTERSIZEMOVE:
        self->Release(); break;
      case WM_KEYDOWN: case WM_SYSKEYDOWN:
        self->Add({"keydown", 0, 0, static_cast<int>(w), (l & (1LL << 30)) != 0});
        if (w == VK_ESCAPE) self->Release();
        break;
      case WM_KEYUP: case WM_SYSKEYUP:
        self->Add({"keyup", 0, 0, static_cast<int>(w)}); break;
      case WM_MOUSEMOVE:
        self->Add({"mousemove", GET_X_LPARAM(l), GET_Y_LPARAM(l)}); break;
      case WM_LBUTTONDOWN: case WM_MBUTTONDOWN: case WM_RBUTTONDOWN:
        self->Add({"mousedown", GET_X_LPARAM(l), GET_Y_LPARAM(l),
            message == WM_LBUTTONDOWN ? 0 : message == WM_MBUTTONDOWN ? 1 : 2}); break;
      case WM_LBUTTONUP: case WM_MBUTTONUP: case WM_RBUTTONUP:
        self->Add({"mouseup", GET_X_LPARAM(l), GET_Y_LPARAM(l),
            message == WM_LBUTTONUP ? 0 : message == WM_MBUTTONUP ? 1 : 2}); break;
      case WM_MOUSEWHEEL:
        self->Add({"wheel", 0, GET_WHEEL_DELTA_WPARAM(w)}); break;
      case WM_INPUT: {
        RAWINPUT input{}; UINT size = sizeof(input);
        const UINT result = GetRawInputData(reinterpret_cast<HRAWINPUT>(l), RID_INPUT,
            &input, &size, sizeof(RAWINPUTHEADER));
        if (result != static_cast<UINT>(-1) && result >= sizeof(RAWINPUTHEADER) &&
            input.header.dwType == RIM_TYPEMOUSE && !(input.data.mouse.usFlags & MOUSE_MOVE_ABSOLUTE)) {
          self->Add({"rawmousemove", static_cast<int>(input.data.mouse.lLastX),
              static_cast<int>(input.data.mouse.lLastY)});
        }
        break; // DefWindowProc performs foreground raw-input cleanup.
      }
      case WM_CAPTURECHANGED:
        if (reinterpret_cast<HWND>(l) != hwnd) self->Release(); break;
      case WM_SETCURSOR:
        if (self->captured && LOWORD(l) == HTCLIENT) { SetCursor(nullptr); return TRUE; }
        break;
      default: break;
    }
    return DefWindowProcW(hwnd, message, w, l);
  }
  Impl(int width, int height) {
    events.reserve(kMaxEvents);
    const auto instance = GetModuleHandleW(nullptr);
    constexpr const wchar_t* class_name = L"KrunkerZeroNativeFixtureWindow";
    WNDCLASSEXW cls{}; cls.cbSize = sizeof(cls); cls.hInstance = instance;
    cls.lpfnWndProc = Procedure; cls.lpszClassName = class_name;
    cls.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    if (!RegisterClassExW(&cls) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS)
      throw std::runtime_error("Win32 window class registration failed");
    // Deliberately fixed-size in this fixture slice. Resizable game surfaces and
    // per-monitor DPI behavior remain acceptance work, not pretend support.
    const DWORD style = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
    RECT rect{0, 0, width, height};
    if (!AdjustWindowRectEx(&rect, style, FALSE, 0)) throw std::runtime_error("Win32 window size calculation failed");
    hwnd = CreateWindowExW(0, class_name, L"Krunker Zero - native Windows fixture (not the game)",
        style, CW_USEDEFAULT, CW_USEDEFAULT, rect.right - rect.left, rect.bottom - rect.top,
        nullptr, nullptr, instance, this);
    if (!hwnd) throw std::runtime_error("Win32 window creation failed: " + std::to_string(GetLastError()));
    // Creation can clamp small captioned windows before WM_NCCREATE installs
    // our instance. Apply the requested size after our handler is available.
    if (!SetWindowPos(hwnd, nullptr, 0, 0, rect.right - rect.left, rect.bottom - rect.top,
                      SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOSENDCHANGING)) {
      const auto error = GetLastError(); DestroyWindow(hwnd); hwnd = nullptr;
      throw std::runtime_error("Win32 window sizing failed: " + std::to_string(error));
    }
    // No RIDEV_INPUTSINK: only receive raw input while this app is foreground.
    RAWINPUTDEVICE device{0x01, 0x02, 0, hwnd};
    if (!RegisterRawInputDevices(&device, 1, sizeof(device))) {
      const auto error = GetLastError(); DestroyWindow(hwnd); hwnd = nullptr;
      throw std::runtime_error("Raw mouse registration failed: " + std::to_string(error));
    }
    ShowWindow(hwnd, SW_SHOW); UpdateWindow(hwnd);
  }
  ~Impl() {
    Release();
    RAWINPUTDEVICE device{0x01, 0x02, RIDEV_REMOVE, nullptr};
    RegisterRawInputDevices(&device, 1, sizeof(device));
    if (hwnd) DestroyWindow(hwnd);
  }
};
Win32Window::Win32Window(int width, int height):impl_(std::make_unique<Impl>(width,height)){}
Win32Window::~Win32Window() = default;
void* Win32Window::Handle() const { return impl_->hwnd; }
void Win32Window::Pump() {
  MSG message{};
  // Bounded message dispatch: a busy input stream cannot starve the JS watchdog.
  for (unsigned count = 0; count < 256 && PeekMessageW(&message, impl_->hwnd, 0, 0, PM_REMOVE); ++count) {
    TranslateMessage(&message); DispatchMessageW(&message);
  }
}
void Win32Window::Close() { impl_->closed = true; impl_->Release(); }
bool Win32Window::Closed() const { return impl_->closed; }
bool Win32Window::Minimized() const { return impl_->minimized; }
bool Win32Window::CapturePointer(bool enable) {
  if (!enable) { impl_->Release(); return false; }
  if (impl_->closed || GetForegroundWindow() != impl_->hwnd) return false;
  RECT rect{};
  if (!GetClientRect(impl_->hwnd, &rect)) throw std::runtime_error("Cannot obtain pointer capture rectangle");
  POINT top{rect.left, rect.top}, bottom{rect.right, rect.bottom};
  if (!ClientToScreen(impl_->hwnd, &top) || !ClientToScreen(impl_->hwnd, &bottom))
    throw std::runtime_error("Cannot translate pointer capture rectangle");
  rect = {top.x, top.y, bottom.x, bottom.y};
  if (!ClipCursor(&rect)) throw std::runtime_error("Pointer clipping failed");
  SetCapture(impl_->hwnd);
  if (GetCapture() != impl_->hwnd) { ClipCursor(nullptr); throw std::runtime_error("Pointer capture failed"); }
  impl_->captured = true; SetCursor(nullptr); return true;
}
std::vector<WindowEvent> Win32Window::DrainEvents() {
  Pump();
  auto events = impl_->events; impl_->events.clear(); return events;
}
std::size_t Win32Window::DroppedEvents() const { return impl_->dropped; }
}  // namespace zero
