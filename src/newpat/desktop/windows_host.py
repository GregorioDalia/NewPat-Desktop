"""Native Windows WebView2 window using the official loader and Python stdlib.

No Python.NET bridge or application-specific native binary is loaded. The COM
ABI below is the base WebView2 Win32 ABI, verified against Microsoft's
Microsoft.Web.WebView2 1.0.4314.35 WebView2.h. Newer runtime interfaces are not
required. Public documentation:
https://learn.microsoft.com/microsoft-edge/webview2/reference/win32/

Only an authenticated loopback origin supplied by the application may navigate
inside the window. The application HTTP service owns RPC and file capabilities.
"""
from __future__ import annotations

import concurrent.futures
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import queue
import struct
import zlib
import subprocess
import sys
import threading
import time
from typing import Callable
from urllib.parse import unquote, urlsplit
import uuid

from newpat.environment import setting
from .host import smoke_probe_script, smoke_ready

HRESULT = C.c_int32
ULONG = C.c_uint32
DWORD = C.c_uint32
UINT = C.c_uint32
BOOL = C.c_int32
LONG = C.c_int32
HWND = C.c_void_p
WPARAM = C.c_size_t
LPARAM = C.c_ssize_t
LRESULT = C.c_ssize_t
PTR = C.c_void_p
WINFUNCTYPE = getattr(C, "WINFUNCTYPE", C.CFUNCTYPE)
S_OK = 0
E_NOINTERFACE = -2147467262
E_POINTER = -2147467261
E_FAIL = -2147467259
WM_DESTROY, WM_SIZE, WM_SETFOCUS, WM_CLOSE = 2, 5, 7, 16
WM_MOVE, WM_TIMER, WM_GETMINMAXINFO, WM_DPICHANGED = 3, 275, 36, 736
WM_DISPATCH = 0x8001
ERROR_CANCELLED_HRESULT = 0x800704C7
IID_IUNKNOWN = "00000000-0000-0000-c000-000000000046"
APP_USER_MODEL_ID = "NewPat.Desktop"


def application_icon() -> Path:
    return Path(__file__).resolve().parents[3] / "assets" / "branding" / "newpat-icon.ico"


class NativeHostError(RuntimeError):
    """An actionable failure of the installed desktop window."""


class GUID(C.Structure):
    _fields_ = [("data1", C.c_uint32), ("data2", C.c_uint16),
                ("data3", C.c_uint16), ("data4", C.c_uint8 * 8)]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


class POINT(C.Structure):
    _fields_ = [("x", LONG), ("y", LONG)]


class RECT(C.Structure):
    _fields_ = [("left", LONG), ("top", LONG), ("right", LONG), ("bottom", LONG)]


class MSG(C.Structure):
    _fields_ = [("hwnd", HWND), ("message", UINT), ("wParam", WPARAM),
                ("lParam", LPARAM), ("time", DWORD), ("pt", POINT), ("lPrivate", DWORD)]


class MINMAXINFO(C.Structure):
    _fields_ = [("ptReserved", POINT), ("ptMaxSize", POINT), ("ptMaxPosition", POINT),
                ("ptMinTrackSize", POINT), ("ptMaxTrackSize", POINT)]


WNDPROC = WINFUNCTYPE(LRESULT, HWND, UINT, WPARAM, LPARAM)


class WNDCLASSEXW(C.Structure):
    _fields_ = [("cbSize", UINT), ("style", UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", C.c_int), ("cbWndExtra", C.c_int),
                ("hInstance", PTR), ("hIcon", PTR), ("hCursor", PTR),
                ("hbrBackground", PTR), ("lpszMenuName", C.c_wchar_p),
                ("lpszClassName", C.c_wchar_p), ("hIconSm", PTR)]


class COMDLG_FILTERSPEC(C.Structure):
    _fields_ = [("pszName", C.c_wchar_p), ("pszSpec", C.c_wchar_p)]


def _check(result: int, operation: str) -> None:
    if result < 0:
        raise NativeHostError(f"{operation} (Windows 0x{result & 0xffffffff:08X}).")


def _method(pointer: PTR | int, slot: int, restype=HRESULT, *argtypes):
    if not pointer:
        raise NativeHostError("Interfaccia grafica Windows non disponibile.")
    vtable = C.cast(pointer, C.POINTER(C.POINTER(PTR))).contents
    return WINFUNCTYPE(restype, PTR, *argtypes)(vtable[slot])


def _call(pointer, slot: int, argtypes=(), *args):
    return _method(pointer, slot, HRESULT, *argtypes)(pointer, *args)


def _release(pointer) -> None:
    if pointer:
        _method(pointer, 2, ULONG)(pointer)


_COM_ROOTS: dict[int, "_Callback"] = {}


class _Callback:
    """A rooted COM callback implementing IUnknown and one Invoke interface."""

    def __init__(self, iid: str, argtypes: tuple, invoke: Callable,
                 on_error: Callable[[Exception], None]):
        self.references = 1
        self.iid = uuid.UUID(iid).bytes_le
        self.on_error = on_error
        qi_type = WINFUNCTYPE(HRESULT, PTR, C.POINTER(GUID), C.POINTER(PTR))
        count_type = WINFUNCTYPE(ULONG, PTR)
        invoke_type = WINFUNCTYPE(HRESULT, PTR, *argtypes)

        def query_interface(_this, requested, output):
            if not output:
                return E_POINTER
            output[0] = None
            if requested and C.string_at(requested, 16) in (
                self.iid, uuid.UUID(IID_IUNKNOWN).bytes_le
            ):
                output[0] = self.pointer
                self.references += 1
                return S_OK
            return E_NOINTERFACE

        def add_ref(_this):
            self.references += 1
            return self.references

        def release(_this):
            self.references = max(0, self.references - 1)
            if self.references == 0:
                _COM_ROOTS.pop(self.pointer.value, None)
            return self.references

        def safe_invoke(_this, *args):
            try:
                invoke(*args)
                return S_OK
            except Exception as exc:  # never unwind into WebView2/Win32
                self.on_error(exc)
                return E_FAIL

        self.functions = (qi_type(query_interface), count_type(add_ref),
                          count_type(release), invoke_type(safe_invoke))
        self.vtable = (PTR * len(self.functions))(
            *(C.cast(function, PTR).value for function in self.functions)
        )
        self.interface = (PTR * 1)(C.cast(self.vtable, PTR).value)
        self.pointer = C.cast(self.interface, PTR)
        _COM_ROOTS[self.pointer.value] = self

    def release_owner(self):
        self.functions[2](self.pointer)


def allowed_navigation(initial_url: str, target_url: str) -> bool:
    """Keep every top/frame navigation inside the initial capability prefix."""
    try:
        initial, target = urlsplit(initial_url), urlsplit(target_url)
        if initial.scheme != "http" or initial.hostname != "127.0.0.1":
            return False
        if not initial.port or initial.username or initial.password:
            return False
        if (target.scheme, target.hostname, target.port) != (
            initial.scheme, initial.hostname, initial.port
        ) or target.username or target.password:
            return False
        parts = initial.path.split("/")
        if len(parts) < 3 or not parts[1]:
            return False
        prefix = "/" + parts[1] + "/"
        path = target.path
        # Double-encoded traversal should not turn into a valid capability URI.
        for _ in range(3):
            decoded = unquote(path)
            if decoded == path:
                break
            path = decoded
        if "\\" in path or any(p in (".", "..") for p in path.split("/")):
            return False
        return path.startswith(prefix)
    except (TypeError, ValueError):
        return False


def _default_loader() -> Path:
    override = setting("WEBVIEW2_LOADER")
    return Path(override) if override else (
        Path(__file__).parent / "native" / "windows" / "x64" / "WebView2Loader.dll"
    )


def verify_dependency(path: Path, manifest_path: Path | None = None) -> None:
    """Verify packaged bytes against the build-time, reviewed dependency record."""
    if not path.is_file():
        raise NativeHostError(f"Componente grafico mancante: {path.name}. Reinstalla NewPat.")
    manifest_path = manifest_path or path.parent.parent / "dependencies.json"
    if not manifest_path.is_file():
        raise NativeHostError("Manifest dei componenti grafici mancante. Reinstalla NewPat.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("files", manifest.get("assets", []))
    if isinstance(entries, dict):
        entries = [{"path": key, **value} if isinstance(value, dict)
                   else {"path": key, "sha256": value} for key, value in entries.items()]
    expected = next((entry.get("sha256") for entry in entries
                     if Path(entry.get("path", entry.get("name", ""))).name == path.name), None)
    if not expected or not isinstance(expected, str) or len(expected) != 64:
        raise NativeHostError(f"Verifica di integrità non disponibile: {path.name}.")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected.lower():
        raise NativeHostError(f"Componente grafico alterato: {path.name}. Reinstalla NewPat.")


_active_host: "_Window | None" = None


def _ui_call(function: Callable):
    host = _active_host
    if host is None:
        raise NativeHostError("La finestra desktop non è aperta.")
    return host.invoke(function)


def _message_box(title: str, message: str, flags: int) -> int:
    if _active_host:
        return _ui_call(lambda: _active_host.user.MessageBoxW(
            _active_host.hwnd, message, title, flags))
    if sys.platform != "win32":
        raise NativeHostError("Questo componente desktop richiede Windows.")
    user = C.WinDLL("user32", use_last_error=True)
    user.MessageBoxW.argtypes = (HWND, C.c_wchar_p, C.c_wchar_p, UINT)
    user.MessageBoxW.restype = C.c_int
    return user.MessageBoxW(None, message, title, flags)


def confirm(title: str, message: str | None = None) -> bool:
    if message is None:
        title, message = "NewPat", title
    return _message_box(title, message, 0x24) == 6


def notify(title: str, message: str) -> None:
    _message_box(title, message, 0x40)


def request_close() -> bool:
    host = _active_host
    return bool(host and not host.destroyed and host.user.PostMessageW(host.hwnd, WM_CLOSE, 0, 0))


def pick_files(title="Seleziona i file", filters=None, multiple=True) -> list[str]:
    return _ui_call(lambda: _active_host.file_dialog(
        "open", title=title, filters=filters, multiple=multiple))


def pick_directory(title="Seleziona una cartella") -> str | None:
    result = _ui_call(lambda: _active_host.file_dialog("folder", title=title))
    return result[0] if result else None


def save_file(title="Salva file", suggested_name="", filters=None) -> str | None:
    result = _ui_call(lambda: _active_host.file_dialog(
        "save", title=title, filters=filters, suggested_name=suggested_name))
    return result[0] if result else None


class _Window:
    def __init__(self, url, title, on_close, loader_path, smoke_test, smoke_report,
                 user_data_dir, timeout, screenshot_path=None):
        if sys.platform != "win32":
            raise NativeHostError("Questo componente desktop richiede Windows.")
        if C.sizeof(PTR) != 8:
            raise NativeHostError("L’interfaccia Windows richiede Python a 64 bit.")
        if not allowed_navigation(url, url):
            raise NativeHostError("Indirizzo locale dell’interfaccia non valido.")
        self.url, self.title, self.on_close = url, title, on_close
        self.loader_path = Path(loader_path) if loader_path else _default_loader()
        self.smoke_test, self.smoke_report = smoke_test, smoke_report
        self.screenshot_path = screenshot_path
        self.user_data_dir = Path(user_data_dir) if user_data_dir else (
            Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NewPat-Desktop" / "webview2"
        )
        self.timeout, self.started = timeout, time.monotonic()
        self.hwnd = None
        self.status_hwnd = None
        self.controller = PTR()
        self.webview = PTR()
        self.environment = PTR()
        self.callbacks: list[_Callback] = []
        self.tasks: queue.Queue = queue.Queue()
        self.thread_id = threading.get_ident()
        self.error: Exception | None = None
        self.com_initialized = False
        self.destroyed = False
        self.runtime_preparing = False
        self.page_loaded = False
        self.smoke_requested = False
        self.smoke_result = None
        self.icons = []
        self.class_name = "NewPatDesktop_" + uuid.uuid4().hex
        self.user = C.WinDLL("user32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.ole = C.WinDLL("ole32", use_last_error=True)
        self._configure_api()

    def _configure_api(self):
        def api(dll, name, result, *args):
            fn = getattr(dll, name)
            fn.restype, fn.argtypes = result, args
            return fn
        api(self.kernel, "GetModuleHandleW", PTR, C.c_wchar_p)
        api(self.user, "RegisterClassExW", C.c_uint16, C.POINTER(WNDCLASSEXW))
        api(self.user, "UnregisterClassW", BOOL, C.c_wchar_p, PTR)
        api(self.user, "CreateWindowExW", HWND, DWORD, C.c_wchar_p, C.c_wchar_p,
            DWORD, C.c_int, C.c_int, C.c_int, C.c_int, HWND, PTR, PTR, PTR)
        api(self.user, "DefWindowProcW", LRESULT, HWND, UINT, WPARAM, LPARAM)
        api(self.user, "DestroyWindow", BOOL, HWND)
        api(self.user, "GetClientRect", BOOL, HWND, C.POINTER(RECT))
        api(self.user, "ShowWindow", BOOL, HWND, C.c_int)
        api(self.user, "UpdateWindow", BOOL, HWND)
        api(self.user, "GetMessageW", BOOL, C.POINTER(MSG), HWND, UINT, UINT)
        api(self.user, "TranslateMessage", BOOL, C.POINTER(MSG))
        api(self.user, "DispatchMessageW", LRESULT, C.POINTER(MSG))
        api(self.user, "PostQuitMessage", None, C.c_int)
        api(self.user, "PostMessageW", BOOL, HWND, UINT, WPARAM, LPARAM)
        api(self.user, "LoadCursorW", PTR, PTR, PTR)
        api(self.user, "LoadImageW", PTR, PTR, C.c_wchar_p, UINT, C.c_int, C.c_int, UINT)
        api(self.user, "DestroyIcon", BOOL, PTR)
        api(self.user, "GetSystemMetrics", C.c_int, C.c_int)
        api(self.user, "MoveWindow", BOOL, HWND, C.c_int, C.c_int, C.c_int, C.c_int, BOOL)
        api(self.user, "SetWindowPos", BOOL, HWND, HWND, C.c_int, C.c_int, C.c_int, C.c_int, UINT)
        api(self.user, "SetWindowTextW", BOOL, HWND, C.c_wchar_p)
        api(self.user, "SetTimer", C.c_size_t, HWND, C.c_size_t, UINT, PTR)
        api(self.user, "KillTimer", BOOL, HWND, C.c_size_t)
        api(self.user, "MessageBoxW", C.c_int, HWND, C.c_wchar_p, C.c_wchar_p, UINT)
        api(self.ole, "CoInitializeEx", HRESULT, PTR, DWORD)
        api(self.ole, "CoUninitialize", None)
        api(self.ole, "CoTaskMemFree", None, PTR)
        api(self.ole, "CoCreateInstance", HRESULT, C.POINTER(GUID), PTR, DWORD,
            C.POINTER(GUID), C.POINTER(PTR))

    def invoke(self, function):
        if self.destroyed:
            raise NativeHostError("La finestra desktop è stata chiusa.")
        if threading.get_ident() == self.thread_id:
            return function()
        future = concurrent.futures.Future()
        self.tasks.put((future, function))
        if not self.user.PostMessageW(self.hwnd, WM_DISPATCH, 0, 0):
            raise NativeHostError("Impossibile comunicare con la finestra desktop.")
        # File dialogs intentionally have no arbitrary short user-response limit.
        return future.result()

    def _dispatch(self):
        while True:
            try:
                future, function = self.tasks.get_nowait()
            except queue.Empty:
                return
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function())
                except Exception as exc:
                    future.set_exception(exc)

    def _callback(self, iid, argtypes, invoke):
        callback = _Callback(iid, argtypes, invoke, self.fail)
        self.callbacks.append(callback)
        return callback.pointer

    def fail(self, exc):
        self.error = exc
        if self.hwnd and not self.destroyed:
            self.user.PostMessageW(self.hwnd, WM_CLOSE, 1, 0)

    def _resize(self):
        rect = RECT()
        self.user.GetClientRect(self.hwnd, C.byref(rect))
        if self.controller:
            _check(_call(self.controller, 6, (RECT,), rect), "Ridimensionamento della finestra")
        elif self.status_hwnd:
            self.user.MoveWindow(self.status_hwnd, 30, 90, max(50, rect.right - 60), 90, True)

    def _window_proc(self, hwnd, message, wparam, lparam):
        try:
            if message == WM_DISPATCH:
                self._dispatch()
                return 0
            if message == WM_SIZE:
                if self.hwnd:
                    self._resize()
                return 0
            if message == WM_MOVE and self.controller:
                _call(self.controller, 23)
                return 0
            if message == WM_SETFOCUS and self.controller:
                _call(self.controller, 12, (C.c_int,), 0)
                return 0
            if message == WM_DPICHANGED:
                rect = C.cast(lparam, C.POINTER(RECT)).contents
                self.user.SetWindowPos(hwnd, None, rect.left, rect.top,
                                       rect.right - rect.left, rect.bottom - rect.top, 0x14)
                return 0
            if message == WM_GETMINMAXINFO:
                info = C.cast(lparam, C.POINTER(MINMAXINFO)).contents
                info.ptMinTrackSize.x, info.ptMinTrackSize.y = 860, 600
                return 0
            if message == WM_TIMER:
                elapsed = time.monotonic() - self.started
                if (not self.page_loaded or (self.smoke_test and self.smoke_result is None)) and not self.runtime_preparing and elapsed > self.timeout:
                    self.fail(NativeHostError("L’interfaccia non si è avviata entro il tempo previsto."))
                elif self.smoke_test and self.page_loaded and not self.smoke_requested:
                    self._smoke_probe()
                return 0
            if message == WM_CLOSE:
                if not self.error and not wparam and self.on_close and self.on_close() is False:
                    return 0
                self.user.DestroyWindow(hwnd)
                return 0
            if message == WM_DESTROY:
                self.destroyed = True
                self.user.KillTimer(hwnd, 1)
                if self.controller:
                    _call(self.controller, 24)
                while True:
                    try:
                        future, _ = self.tasks.get_nowait()
                        future.set_exception(NativeHostError("La finestra desktop è stata chiusa."))
                    except queue.Empty:
                        break
                self.user.PostQuitMessage(1 if self.error else 0)
                return 0
        except Exception as exc:
            self.fail(exc)
            return 0
        return self.user.DefWindowProcW(hwnd, message, wparam, lparam)

    def _create_window(self):
        _check(self.ole.CoInitializeEx(None, 2), "Inizializzazione dell’interfaccia Windows")
        self.com_initialized = True
        # A pythonw host must identify the actual application before creating
        # its window, otherwise Explorer groups it under Python's taskbar icon.
        shell = C.WinDLL("shell32", use_last_error=True)
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes = (C.c_wchar_p,)
        shell.SetCurrentProcessExplicitAppUserModelID.restype = HRESULT
        _check(shell.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID),
               "Identità dell’applicazione NewPat")
        try:
            dpi = self.user.SetProcessDpiAwarenessContext
            dpi.argtypes, dpi.restype = (PTR,), BOOL
            dpi(PTR(-4 & ((1 << (8 * C.sizeof(PTR))) - 1)))
        except AttributeError:
            pass
        self.instance = self.kernel.GetModuleHandleW(None)
        self.wndproc = WNDPROC(self._window_proc)
        klass = WNDCLASSEXW()
        klass.cbSize, klass.style = C.sizeof(klass), 3
        klass.lpfnWndProc, klass.hInstance = self.wndproc, self.instance
        klass.hCursor = self.user.LoadCursorW(None, PTR(32512))
        icon_path = application_icon()
        if icon_path.is_file():
            for size in (32, 16):
                icon = self.user.LoadImageW(None, str(icon_path), 1, size, size, 0x10)
                if not icon:
                    raise C.WinError(C.get_last_error())
                self.icons.append(icon)
            klass.hIcon, klass.hIconSm = self.icons
        klass.hbrBackground, klass.lpszClassName = PTR(6), self.class_name
        if not self.user.RegisterClassExW(C.byref(klass)):
            raise C.WinError(C.get_last_error())
        width = min(1440, max(900, self.user.GetSystemMetrics(0) - 100))
        height = min(960, max(650, self.user.GetSystemMetrics(1) - 100))
        self.hwnd = self.user.CreateWindowExW(0, self.class_name, self.title, 0x00CF0000,
            0x80000000 - (1 << 32), 0x80000000 - (1 << 32), width, height,
            None, None, self.instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        self.status_hwnd = self.user.CreateWindowExW(0, "STATIC",
            "Preparazione dell’interfaccia NewPat…", 0x50000001,
            30, 90, width - 60, 90, self.hwnd, None, self.instance, None)
        self.user.ShowWindow(self.hwnd, 5)
        self.user.UpdateWindow(self.hwnd)
        self.user.SetTimer(self.hwnd, 1, 1000, None)

    def _load_loader(self):
        verify_dependency(self.loader_path)
        self.loader = C.WinDLL(str(self.loader_path.resolve()), winmode=0x900)
        self.loader.GetAvailableCoreWebView2BrowserVersionString.argtypes = (
            C.c_wchar_p, C.POINTER(PTR))
        self.loader.GetAvailableCoreWebView2BrowserVersionString.restype = HRESULT
        self.loader.CreateCoreWebView2EnvironmentWithOptions.argtypes = (
            C.c_wchar_p, C.c_wchar_p, PTR, PTR)
        self.loader.CreateCoreWebView2EnvironmentWithOptions.restype = HRESULT

    def _runtime_available(self):
        version = PTR()
        result = self.loader.GetAvailableCoreWebView2BrowserVersionString(
            setting("WEBVIEW2_RUNTIME"), C.byref(version))
        if version:
            self.runtime_version = C.wstring_at(version)
            self.ole.CoTaskMemFree(version)
        return result >= 0 and bool(version)

    def _prepare(self):
        self._load_loader()
        if self._runtime_available():
            self._create_environment()
            return
        installer = self.loader_path.with_name("MicrosoftEdgeWebview2Setup.exe")
        verify_dependency(installer)
        self.runtime_preparing = True
        self.user.SetWindowTextW(self.status_hwnd,
            "Preparazione del componente grafico Microsoft WebView2.\n"
            "Il primo avvio può richiedere alcuni minuti e una connessione Internet.")

        def install():
            try:
                result = subprocess.run([str(installer.resolve()), "/silent", "/install"],
                    check=False, timeout=600, creationflags=0x08000000,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if result.returncode not in (0, 3010):
                    raise NativeHostError("Preparazione di Microsoft WebView2 non riuscita "
                        f"(codice {result.returncode}). Verifica la connessione e riavvia NewPat.")
                def ready():
                    self.runtime_preparing = False
                    self.started = time.monotonic()
                    if not self._runtime_available():
                        raise NativeHostError("Microsoft WebView2 non è disponibile. "
                            "Riavvia Windows e apri nuovamente NewPat.")
                    self._create_environment()
                self.invoke(ready)
            except Exception as exc:
                self.runtime_preparing = False
                self.fail(exc)
        threading.Thread(target=install, name="NewPat-WebView2-setup", daemon=True).start()

    def _create_environment(self):
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        handler = self._callback("4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d",
                                 (HRESULT, PTR), self._environment_ready)
        _check(self.loader.CreateCoreWebView2EnvironmentWithOptions(
            setting("WEBVIEW2_RUNTIME"), str(self.user_data_dir.resolve()),
            None, handler), "Avvio di Microsoft WebView2")

    def _environment_ready(self, result, environment):
        _check(result, "Preparazione della finestra grafica")
        if self.destroyed:
            return
        self.environment = PTR(environment)
        _method(self.environment, 1, ULONG)(self.environment)
        handler = self._callback("6c4819f3-c9b7-4260-8127-c9f5bde7f68c",
                                 (HRESULT, PTR), self._controller_ready)
        _check(_call(self.environment, 3, (HWND, PTR), self.hwnd, handler),
               "Creazione della finestra grafica")

    def _event(self, slot, iid, function):
        handler = self._callback(iid, (PTR, PTR), function)
        token = C.c_int64()
        _check(_call(self.webview, slot, (PTR, C.POINTER(C.c_int64)), handler, C.byref(token)),
               "Configurazione degli eventi della finestra")

    def _controller_ready(self, result, controller):
        _check(result, "Creazione della finestra grafica")
        if self.destroyed:
            return
        self.controller = PTR(controller)
        _method(self.controller, 1, ULONG)(self.controller)
        _check(_call(self.controller, 25, (C.POINTER(PTR),), C.byref(self.webview)),
               "Collegamento dell’interfaccia")
        settings = PTR()
        _check(_call(self.webview, 3, (C.POINTER(PTR),), C.byref(settings)),
               "Configurazione dell’interfaccia")
        try:
            # No debugger, host objects, context-menu navigation or status bar.
            for slot in (10, 12, 14, 16):
                _check(_call(settings, slot, (BOOL,), False), "Configurazione di WebView2")
        finally:
            _release(settings)
        self._event(7, "9adbe429-f36d-432b-9ddc-f8881fbd76e3", self._navigation_starting)
        self._event(17, "9adbe429-f36d-432b-9ddc-f8881fbd76e3", self._navigation_starting)
        self._event(15, "d33a35bf-1c49-4f98-93ab-006e0533fe1c", self._navigation_completed)
        self._event(44, "d4c185fe-c81c-4989-97af-2d3fa7ab5651", self._new_window)
        self._event(23, "15e1c6a3-c72a-4df3-91d7-d097fbec6bfd", self._permission)
        self._resize()
        _check(_call(self.controller, 4, (BOOL,), True), "Visualizzazione dell’interfaccia")
        if self.status_hwnd:
            self.user.DestroyWindow(self.status_hwnd)
            self.status_hwnd = None
        _check(_call(self.webview, 5, (C.c_wchar_p,), self.url), "Apertura dell’interfaccia NewPat")

    def _navigation_starting(self, _sender, args):
        uri = PTR()
        _check(_call(args, 3, (C.POINTER(PTR),), C.byref(uri)), "Verifica della navigazione")
        try:
            permitted = allowed_navigation(self.url, C.wstring_at(uri) if uri else "")
        finally:
            if uri:
                self.ole.CoTaskMemFree(uri)
        if not permitted:
            _check(_call(args, 8, (BOOL,), True), "Blocco della navigazione esterna")

    def _navigation_completed(self, _sender, args):
        success = BOOL()
        _check(_call(args, 3, (C.POINTER(BOOL),), C.byref(success)), "Verifica della pagina")
        if success.value:
            self.page_loaded = True
        elif not self.page_loaded:
            raise NativeHostError("Impossibile caricare l’interfaccia locale di NewPat.")

    def _new_window(self, _sender, args):
        _check(_call(args, 6, (BOOL,), True), "Blocco delle finestre esterne")

    def _permission(self, _sender, args):
        # App files use explicit native dialogs and scoped capabilities. Web content
        # receives no camera, microphone, geolocation, notification or clipboard grant.
        _check(_call(args, 7, (C.c_int,), 2), "Gestione dei permessi del componente grafico")

    def _smoke_probe(self):
        self.smoke_requested = True
        handler = self._callback("49511172-cc67-4bca-9923-137112f4c4cc",
                                 (HRESULT, C.c_wchar_p), self._smoke_done)
        code = smoke_probe_script()
        _check(_call(self.webview, 29, (C.c_wchar_p, PTR), code, handler),
               "Verifica della finestra desktop")

    def _smoke_done(self, result, encoded):
        _check(result, "Verifica JavaScript del componente grafico")
        data = json.loads(encoded)
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict) and not smoke_ready(data):
            self.smoke_requested = False
            return
        if not isinstance(data, dict) or not data.get("nativeWebView") or not data.get("bodyText"):
            raise NativeHostError("La verifica della finestra desktop non è riuscita.")
        data.update(status="passed", host="win32-webview2", runtime_version=self.runtime_version,
                    app_user_model_id=APP_USER_MODEL_ID, application_icon_loaded=len(self.icons) == 2)
        if self.screenshot_path:
            self.capture_png(Path(self.screenshot_path))
            data["screenshot"] = str(self.screenshot_path)
        self.smoke_result = data
        if self.smoke_report:
            output = Path(self.smoke_report)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.user.PostMessageW(self.hwnd, WM_CLOSE, 1, 0)

    def capture_png(self, output: Path):
        """Capture this visible native window; encode PNG using only stdlib."""
        gdi = C.WinDLL("gdi32", use_last_error=True)
        self.user.GetWindowRect.argtypes, self.user.GetWindowRect.restype = (HWND, C.POINTER(RECT)), BOOL
        self.user.GetDC.argtypes, self.user.GetDC.restype = (HWND,), PTR
        self.user.ReleaseDC.argtypes, self.user.ReleaseDC.restype = (HWND, PTR), C.c_int
        self.user.PrintWindow.argtypes, self.user.PrintWindow.restype = (HWND, PTR, UINT), BOOL
        gdi.CreateCompatibleDC.argtypes, gdi.CreateCompatibleDC.restype = (PTR,), PTR
        gdi.CreateDIBSection.argtypes, gdi.CreateDIBSection.restype = (PTR, PTR, UINT, C.POINTER(PTR), PTR, DWORD), PTR
        gdi.SelectObject.argtypes, gdi.SelectObject.restype = (PTR, PTR), PTR
        gdi.DeleteObject.argtypes, gdi.DeleteObject.restype = (PTR,), BOOL
        gdi.DeleteDC.argtypes, gdi.DeleteDC.restype = (PTR,), BOOL
        gdi.BitBlt.argtypes, gdi.BitBlt.restype = (PTR, C.c_int, C.c_int, C.c_int, C.c_int, PTR, C.c_int, C.c_int, DWORD), BOOL
        rect = RECT()
        if not self.user.GetWindowRect(self.hwnd, C.byref(rect)):
            raise NativeHostError("Impossibile acquisire la finestra desktop.")
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            raise NativeHostError("Dimensioni della finestra non valide.")
        screen = self.user.GetDC(None)
        memory = gdi.CreateCompatibleDC(screen)
        bits = PTR()
        # BITMAPINFOHEADER, followed by unused RGBQUAD storage.
        header = C.create_string_buffer(struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32,
                                                    0, width * height * 4, 0, 0, 0, 0) + bytes(4))
        bitmap = gdi.CreateDIBSection(memory, header, 0, C.byref(bits), None, 0)
        if not bitmap or not bits:
            if memory: gdi.DeleteDC(memory)
            if screen: self.user.ReleaseDC(None, screen)
            raise NativeHostError("Impossibile acquisire i pixel della finestra desktop.")
        previous = gdi.SelectObject(memory, bitmap)
        try:
            captured = self.user.PrintWindow(self.hwnd, memory, 2)
            if not captured:
                captured = gdi.BitBlt(memory, 0, 0, width, height, screen,
                                      rect.left, rect.top, 0x40CC0020)
            if not captured:
                raise NativeHostError("Acquisizione della finestra desktop non riuscita.")
            bgra = C.string_at(bits, width * height * 4)
            # Some Chromium compositors return a black PrintWindow surface.
            if not any(bgra[0::4]) and not any(bgra[1::4]) and not any(bgra[2::4]):
                if not gdi.BitBlt(memory, 0, 0, width, height, screen, rect.left, rect.top, 0x40CC0020):
                    raise NativeHostError("Il compositor non ha restituito pixel visibili.")
                bgra = C.string_at(bits, width * height * 4)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(encode_bgra_png(bgra, width, height))
        finally:
            gdi.SelectObject(memory, previous)
            gdi.DeleteObject(bitmap)
            gdi.DeleteDC(memory)
            self.user.ReleaseDC(None, screen)

    def file_dialog(self, kind, *, title, filters=None, multiple=False, suggested_name=""):
        save = kind == "save"
        clsid = GUID.from_string("c0b4e2f3-ba21-4773-8dba-335ec946eb8b" if save
                                 else "dc1c5a9c-e88a-4dde-a5a1-60f82a20aef7")
        iid = GUID.from_string("84bccd23-5fde-4cdb-aea4-af64b83d78ab" if save
                               else "d57c7288-d4ad-4768-be02-9d969532d960")
        dialog = PTR()
        _check(self.ole.CoCreateInstance(C.byref(clsid), None, 1, C.byref(iid), C.byref(dialog)),
               "Apertura della finestra di selezione")
        try:
            options = DWORD()
            _check(_call(dialog, 10, (C.POINTER(DWORD),), C.byref(options)), "Lettura delle opzioni")
            options.value |= 0x40 | 0x8  # filesystem items, never change working directory
            if kind == "folder":
                options.value |= 0x20 | 0x800
            elif save:
                options.value |= 0x2 | 0x800  # overwrite prompt, path exists
            else:
                options.value |= 0x1000 | 0x800  # file/path must exist
                if multiple:
                    options.value |= 0x200
            _check(_call(dialog, 9, (DWORD,), options), "Impostazione della selezione")
            _check(_call(dialog, 17, (C.c_wchar_p,), title), "Titolo della selezione")
            if suggested_name:
                _check(_call(dialog, 15, (C.c_wchar_p,), suggested_name), "Nome del file")
            if filters:
                pairs = normalize_filters(filters)
                specs = (COMDLG_FILTERSPEC * len(pairs))(
                    *(COMDLG_FILTERSPEC(label, pattern) for label, pattern in pairs))
                _check(_call(dialog, 4, (UINT, C.POINTER(COMDLG_FILTERSPEC)), len(pairs), specs),
                       "Filtri dei file")
            result = _call(dialog, 3, (HWND,), self.hwnd)
            if (result & 0xffffffff) == ERROR_CANCELLED_HRESULT:
                return []
            _check(result, "Selezione del file")
            if multiple and not save and kind != "folder":
                items = PTR()
                _check(_call(dialog, 27, (C.POINTER(PTR),), C.byref(items)), "Lettura dei file scelti")
                try:
                    count = DWORD()
                    _check(_call(items, 7, (C.POINTER(DWORD),), C.byref(count)), "Conteggio dei file")
                    paths = []
                    for index in range(count.value):
                        item = PTR()
                        _check(_call(items, 8, (DWORD, C.POINTER(PTR)), index, C.byref(item)),
                               "Lettura del file scelto")
                        try:
                            paths.append(self._shell_path(item))
                        finally:
                            _release(item)
                    return paths
                finally:
                    _release(items)
            item = PTR()
            _check(_call(dialog, 20, (C.POINTER(PTR),), C.byref(item)), "Lettura della selezione")
            try:
                return [self._shell_path(item)]
            finally:
                _release(item)
        finally:
            _release(dialog)

    def _shell_path(self, item):
        path = PTR()
        _check(_call(item, 5, (UINT, C.POINTER(PTR)), 0x80058000, C.byref(path)),
               "Lettura del percorso del file")
        try:
            return C.wstring_at(path)
        finally:
            self.ole.CoTaskMemFree(path)

    def run(self):
        try:
            self._create_window()
            try:
                self._prepare()
            except Exception as exc:
                self.fail(exc)
            message = MSG()
            while True:
                status = self.user.GetMessageW(C.byref(message), None, 0, 0)
                if status == -1:
                    raise C.WinError(C.get_last_error())
                if status == 0:
                    break
                self.user.TranslateMessage(C.byref(message))
                self.user.DispatchMessageW(C.byref(message))
            if self.error:
                raise NativeHostError(str(self.error)) from self.error
            return 0
        finally:
            if self.hwnd and not self.destroyed:
                self.user.DestroyWindow(self.hwnd)
            _release(self.webview)
            _release(self.controller)
            _release(self.environment)
            self.user.UnregisterClassW(self.class_name, getattr(self, "instance", None))
            for icon in self.icons:
                self.user.DestroyIcon(icon)
            if self.com_initialized:
                self.ole.CoUninitialize()
            for callback in self.callbacks:
                callback.release_owner()


def encode_bgra_png(bgra: bytes, width: int, height: int) -> bytes:
    if width <= 0 or height <= 0 or len(bgra) != width * height * 4:
        raise ValueError("Invalid screenshot dimensions")
    rows = []
    for offset in range(0, len(bgra), width * 4):
        row = bgra[offset:offset + width * 4]
        rgba = bytearray(len(row))
        rgba[0::4], rgba[1::4], rgba[2::4] = row[2::4], row[1::4], row[0::4]
        rgba[3::4] = b"\xff" * width
        rows.append(b"\0" + rgba)
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b""))


def normalize_filters(filters) -> list[tuple[str, str]]:
    """Accept named native-dialog filters without embedding nulls in Win32 strings."""
    pairs = []
    for entry in filters:
        if isinstance(entry, str):
            label, pattern = entry, entry
        elif isinstance(entry, dict):
            label = entry.get("label", entry.get("name", "File"))
            pattern = entry.get("pattern", entry.get("extensions", "*.*"))
        else:
            label, pattern = entry
        if isinstance(pattern, (list, tuple)):
            pattern = ";".join(p if p.startswith("*") else "*." + p.lstrip(".") for p in pattern)
        if not isinstance(label, str) or not isinstance(pattern, str) or "\0" in label + pattern:
            raise ValueError("Filtro del file non valido.")
        pairs.append((label, pattern))
    return pairs or [("Tutti i file", "*.*")]


def run_window(url: str, title: str = "NewPat", on_close=None, *, loader_path=None,
               smoke_test=False, smoke_report=None, user_data_dir=None, timeout=60,
               screenshot_path=None) -> int:
    """Run one native desktop window on its calling (STA/UI) thread.

    ``on_close`` may return False to keep an active analysis window open. Native
    dialogs called by RPC workers are marshalled to this UI thread. The caller
    owns the loopback service lifetime. The desktop workspace stays in WebView2.
    """
    global _active_host
    if _active_host is not None:
        raise NativeHostError("Una finestra NewPat è già aperta in questo processo.")
    host = _Window(url, title, on_close, loader_path, smoke_test, smoke_report,
                   user_data_dir, timeout, screenshot_path)
    _active_host = host
    try:
        return host.run()
    finally:
        _active_host = None
