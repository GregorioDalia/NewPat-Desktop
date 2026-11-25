"""macOS application window backed by the system Cocoa/WKWebView frameworks.

Uses the Objective-C runtime and Apple's documented Blocks ABI through ctypes.
No downloaded native bridge, Python extension or external browser is required.
Reference: https://clang.llvm.org/docs/Block-ABI-Apple.html and WKNavigationDelegate.
"""
from __future__ import annotations

import concurrent.futures
import ctypes as C
import json
from pathlib import Path
import queue
import sys
import threading
import time
import uuid

from .host import smoke_probe_script, smoke_ready
from .windows_host import NativeHostError, allowed_navigation, normalize_filters

PTR = C.c_void_p
BOOL = C.c_bool
NSInteger = C.c_int64
NSUInteger = C.c_uint64
CGFloat = C.c_double


class CGPoint(C.Structure):
    _fields_ = [("x", CGFloat), ("y", CGFloat)]


class CGSize(C.Structure):
    _fields_ = [("width", CGFloat), ("height", CGFloat)]


class CGRect(C.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]


class _BlockDescriptor(C.Structure):
    _fields_ = [("reserved", C.c_uint64), ("size", C.c_uint64), ("signature", C.c_char_p)]


class _BlockLiteral(C.Structure):
    _fields_ = [("isa", PTR), ("flags", C.c_int32), ("reserved", C.c_int32),
                ("invoke", PTR), ("descriptor", C.POINTER(_BlockDescriptor))]


# Objective-C retains IMPs/Blocks independently of Python's garbage collector.
# Root their tiny ctypes descriptors for the process lifetime, including any
# asynchronous WebKit completion delivered after the window closes.
_NATIVE_ROOTS: list = []
_active_host: "_Window | None" = None


def _invoke_decision(block_pointer, decision: int):
    block = C.cast(block_pointer, C.POINTER(_BlockLiteral)).contents
    C.CFUNCTYPE(None, PTR, NSInteger)(block.invoke)(block_pointer, decision)


class _Cocoa:
    def __init__(self):
        if sys.platform != "darwin":
            raise NativeHostError("Questo componente desktop richiede macOS.")
        if threading.current_thread() is not threading.main_thread():
            raise NativeHostError("L’interfaccia macOS deve partire dal thread principale.")
        self.objc = C.CDLL("/usr/lib/libobjc.A.dylib")
        self.system = C.CDLL("/usr/lib/libSystem.B.dylib")
        self.foundation = C.CDLL("/System/Library/Frameworks/Foundation.framework/Foundation")
        self.appkit = C.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        self.webkit = C.CDLL("/System/Library/Frameworks/WebKit.framework/WebKit")
        self.objc.objc_getClass.argtypes, self.objc.objc_getClass.restype = [C.c_char_p], PTR
        self.objc.sel_registerName.argtypes, self.objc.sel_registerName.restype = [C.c_char_p], PTR
        self.objc.objc_allocateClassPair.argtypes = [PTR, C.c_char_p, C.c_size_t]
        self.objc.objc_allocateClassPair.restype = PTR
        self.objc.objc_registerClassPair.argtypes, self.objc.objc_registerClassPair.restype = [PTR], None
        self.objc.class_addMethod.argtypes = [PTR, PTR, PTR, C.c_char_p]
        self.objc.class_addMethod.restype = BOOL
        self.functions = {}
        self.selectors = {}
        self.msg_address = C.cast(self.objc.objc_msgSend, PTR).value

    def cls(self, name):
        result = self.objc.objc_getClass(name.encode())
        if not result:
            raise NativeHostError(f"Componente macOS non disponibile: {name}.")
        return result

    def sel(self, name):
        if name not in self.selectors:
            self.selectors[name] = self.objc.sel_registerName(name.encode())
        return self.selectors[name]

    def send(self, obj, selector, result=PTR, argtypes=(), *args):
        key = (result, tuple(argtypes))
        if key not in self.functions:
            self.functions[key] = C.CFUNCTYPE(result, PTR, PTR, *argtypes)(self.msg_address)
        return self.functions[key](obj, self.sel(selector), *args)

    def string(self, text):
        return self.send(self.cls("NSString"), "stringWithUTF8String:", PTR,
                         (C.c_char_p,), str(text).encode("utf-8"))

    def python_string(self, obj):
        if not obj:
            return ""
        raw = self.send(obj, "UTF8String", C.c_char_p)
        return raw.decode("utf-8") if raw else ""

    def allocate(self, name):
        return self.send(self.send(self.cls(name), "alloc"), "init")

    def method(self, klass, selector, result, argtypes, encoding, function, on_error):
        def wrapped(_self, _cmd, *args):
            try:
                return function(*args)
            except Exception as exc:
                on_error(exc)
                return False if result is BOOL else None
        callback = C.CFUNCTYPE(result, PTR, PTR, *argtypes)(wrapped)
        _NATIVE_ROOTS.append(callback)
        if not self.objc.class_addMethod(klass, self.sel(selector), C.cast(callback, PTR), encoding):
            raise NativeHostError(f"Impossibile configurare il componente macOS: {selector}.")

    def completion_block(self, function, on_error):
        def invoke(_block, value, error):
            try:
                function(value, error)
            except Exception as exc:
                on_error(exc)
        callback = C.CFUNCTYPE(None, PTR, PTR, PTR)(invoke)
        descriptor = _BlockDescriptor(0, C.sizeof(_BlockLiteral), b"v@?@@")
        block_class = (PTR * 32).in_dll(self.system, "_NSConcreteGlobalBlock")
        literal = _BlockLiteral(C.addressof(block_class), (1 << 28) | (1 << 30), 0,
                                C.cast(callback, PTR), C.pointer(descriptor))
        _NATIVE_ROOTS.append((callback, descriptor, literal, block_class))
        return C.cast(C.pointer(literal), PTR)


class _Window:
    def __init__(self, url, title, on_close, smoke_test, smoke_report, timeout, screenshot_path=None):
        if not allowed_navigation(url, url):
            raise NativeHostError("Indirizzo locale dell’interfaccia non valido.")
        self.cocoa = c = _Cocoa()
        self.url, self.title, self.on_close = url, title, on_close
        self.smoke_test, self.smoke_report, self.timeout = smoke_test, smoke_report, timeout
        self.screenshot_path = screenshot_path
        self.started = time.monotonic()
        self.page_loaded = False
        self.smoke_requested = False
        self.smoke_result = None
        self.closed = False
        self.error = None
        self.tasks = queue.Queue()
        self.tasks_lock = threading.Lock()
        self.thread_id = threading.get_ident()
        self.pool = c.allocate("NSAutoreleasePool")
        self.app = c.send(c.cls("NSApplication"), "sharedApplication")
        c.send(self.app, "setActivationPolicy:", BOOL, (NSInteger,), 0)
        self.window = None
        self.webview = None
        self.timer = None
        self.delegate = None
        self._make_delegate()

    def _make_delegate(self):
        c = self.cocoa
        klass = c.objc.objc_allocateClassPair(c.cls("NSObject"),
            ("NIPATDelegate_" + uuid.uuid4().hex).encode(), 0)
        if not klass:
            raise NativeHostError("Impossibile creare la finestra NewPat.")
        methods = [
            ("windowShouldClose:", BOOL, (PTR,), b"B@:@", self._should_close),
            ("windowWillClose:", None, (PTR,), b"v@:@", self._will_close),
            ("tick:", None, (PTR,), b"v@:@", self._tick),
            ("requestClose:", None, (PTR,), b"v@:@", lambda _: self.request_close()),
            ("webView:decidePolicyForNavigationAction:decisionHandler:", None,
             (PTR, PTR, PTR), b"v@:@@@?", self._decide_navigation),
            ("webView:didFinishNavigation:", None, (PTR, PTR), b"v@:@@", self._did_finish),
            ("webView:didFailProvisionalNavigation:withError:", None,
             (PTR, PTR, PTR), b"v@:@@@", self._did_fail),
            ("webView:didFailNavigation:withError:", None,
             (PTR, PTR, PTR), b"v@:@@@", self._did_fail),
            ("webViewWebContentProcessDidTerminate:", None, (PTR,), b"v@:@",
             lambda _: self.fail(NativeHostError("Il componente grafico macOS si è interrotto."))),
            ("webView:createWebViewWithConfiguration:forNavigationAction:windowFeatures:",
             PTR, (PTR, PTR, PTR, PTR), b"@@:@@@@", lambda *_: None),
        ]
        for selector, result, args, encoding, function in methods:
            c.method(klass, selector, result, args, encoding, function, self.fail)
        c.objc.objc_registerClassPair(klass)
        self.delegate = c.send(c.send(klass, "alloc"), "init")

    def invoke(self, function):
        if self.closed:
            raise NativeHostError("La finestra desktop è stata chiusa.")
        if threading.get_ident() == self.thread_id:
            return function()
        return self._queue_task(function).result()

    def _queue_task(self, function):
        future = concurrent.futures.Future()
        with self.tasks_lock:
            if self.closed:
                future.set_exception(NativeHostError("La finestra desktop è stata chiusa."))
            else:
                self.tasks.put((future, function))
        return future

    def fail(self, exc):
        self.error = exc
        if self.window:
            # All WebKit/delegate callbacks occur on the main thread. An RPC
            # worker instead schedules the close through the timer queue.
            if threading.get_ident() == self.thread_id:
                self.cocoa.send(self.window, "close", None)
            else:
                self._queue_task(lambda: self.cocoa.send(self.window, "close", None))

    def _tick(self, _timer):
        while True:
            try:
                future, function = self.tasks.get_nowait()
            except queue.Empty:
                break
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(function())
                except Exception as exc:
                    future.set_exception(exc)
        if self.closed:
            return
        if (not self.page_loaded or (self.smoke_test and self.smoke_result is None)) and (
            time.monotonic() - self.started > self.timeout
        ):
            self.fail(NativeHostError("L’interfaccia non si è avviata entro il tempo previsto."))
        elif self.smoke_test and self.page_loaded and not self.smoke_requested:
            self._smoke_probe()

    def _should_close(self, _window):
        return bool(self.error or not self.on_close or self.on_close() is not False)

    def _close_tasks(self):
        with self.tasks_lock:
            if self.closed:
                return False
            self.closed = True
        while True:
            try:
                future, _ = self.tasks.get_nowait()
                future.set_exception(NativeHostError("La finestra desktop è stata chiusa."))
            except queue.Empty:
                return True

    def _will_close(self, _notification):
        if not self._close_tasks():
            return
        c = self.cocoa
        c.send(self.app, "stop:", None, (PTR,), None)
        # stop: called from a timer or WebKit completion does not wake run's
        # next-event wait. Post an application-defined event so closing cannot
        # depend on a subsequent keyboard/mouse event from the user.
        event = c.send(c.cls("NSEvent"),
            "otherEventWithType:location:modifierFlags:timestamp:windowNumber:context:subtype:data1:data2:",
            PTR, (NSUInteger, CGPoint, NSUInteger, C.c_double, NSInteger, PTR, C.c_short, NSInteger, NSInteger),
            13, CGPoint(0, 0), 0, 0.0, 0, None, 0, 0, 0)
        c.send(self.app, "postEvent:atStart:", None, (PTR, BOOL), event, False)

    def request_close(self):
        if not self.closed and self.window:
            self.cocoa.send(self.window, "performClose:", None, (PTR,), None)
            return True
        return False

    def _decide_navigation(self, _webview, action, decision):
        c = self.cocoa
        request = c.send(action, "request")
        url = c.send(c.send(request, "URL"), "absoluteString")
        _invoke_decision(decision, 1 if allowed_navigation(self.url, c.python_string(url)) else 0)

    def _did_finish(self, _webview, _navigation):
        self.page_loaded = True

    def _did_fail(self, _webview, _navigation, error):
        if not self.page_loaded:
            description = self.cocoa.python_string(self.cocoa.send(error, "localizedDescription"))
            self.fail(NativeHostError("Impossibile caricare l’interfaccia locale: " + description))

    def _menu(self):
        c = self.cocoa
        main = c.allocate("NSMenu")
        app_item = c.allocate("NSMenuItem")
        app_menu = c.allocate("NSMenu")
        quit_item = c.send(c.send(c.cls("NSMenuItem"), "alloc"),
            "initWithTitle:action:keyEquivalent:", PTR, (PTR, PTR, PTR),
            c.string("Chiudi NewPat"), c.sel("requestClose:"), c.string("q"))
        c.send(quit_item, "setTarget:", None, (PTR,), self.delegate)
        c.send(app_menu, "addItem:", None, (PTR,), quit_item)
        c.send(app_item, "setSubmenu:", None, (PTR,), app_menu)
        c.send(main, "addItem:", None, (PTR,), app_item)
        edit_item = c.allocate("NSMenuItem")
        c.send(edit_item, "setTitle:", None, (PTR,), c.string("Modifica"))
        edit = c.allocate("NSMenu")
        c.send(edit, "setTitle:", None, (PTR,), c.string("Modifica"))
        for title, selector, key in [("Taglia", "cut:", "x"), ("Copia", "copy:", "c"),
                                     ("Incolla", "paste:", "v"), ("Seleziona tutto", "selectAll:", "a")]:
            item = c.send(c.send(c.cls("NSMenuItem"), "alloc"),
                "initWithTitle:action:keyEquivalent:", PTR, (PTR, PTR, PTR),
                c.string(title), c.sel(selector), c.string(key))
            c.send(edit, "addItem:", None, (PTR,), item)
            c.send(item, "release", None)
        c.send(edit_item, "setSubmenu:", None, (PTR,), edit)
        c.send(main, "addItem:", None, (PTR,), edit_item)
        c.send(self.app, "setMainMenu:", None, (PTR,), main)
        for item in (quit_item, app_menu, app_item, edit, edit_item, main):
            c.send(item, "release", None)

    def _create(self):
        c = self.cocoa
        rect = CGRect(CGPoint(0, 0), CGSize(1320, 860))
        self.window = c.send(c.send(c.cls("NSWindow"), "alloc"),
            "initWithContentRect:styleMask:backing:defer:", PTR,
            (CGRect, NSUInteger, NSUInteger, BOOL), rect, 15, 2, False)
        if not self.window:
            raise NativeHostError("Impossibile creare la finestra desktop macOS.")
        c.send(self.window, "setReleasedWhenClosed:", None, (BOOL,), False)
        c.send(self.window, "setTitle:", None, (PTR,), c.string(self.title))
        c.send(self.window, "setMinSize:", None, (CGSize,), CGSize(860, 600))
        c.send(self.window, "setDelegate:", None, (PTR,), self.delegate)
        configuration = c.allocate("WKWebViewConfiguration")
        # Native preferences/results are persisted by NIPAT. Web content has an
        # ephemeral cache, so no genomic paths leak into a shared Safari profile.
        store = c.send(c.cls("WKWebsiteDataStore"), "nonPersistentDataStore")
        c.send(configuration, "setWebsiteDataStore:", None, (PTR,), store)
        preferences = c.send(configuration, "preferences")
        c.send(preferences, "setJavaScriptCanOpenWindowsAutomatically:", None, (BOOL,), False)
        self.webview = c.send(c.send(c.cls("WKWebView"), "alloc"),
            "initWithFrame:configuration:", PTR, (CGRect, PTR), rect, configuration)
        c.send(configuration, "release", None)
        if not self.webview:
            raise NativeHostError("Il componente grafico WKWebView non è disponibile.")
        c.send(self.webview, "setNavigationDelegate:", None, (PTR,), self.delegate)
        c.send(self.webview, "setUIDelegate:", None, (PTR,), self.delegate)
        c.send(self.webview, "setAutoresizingMask:", None, (NSUInteger,), 18)
        if c.send(self.webview, "respondsToSelector:", BOOL, (PTR,), c.sel("setInspectable:")):
            c.send(self.webview, "setInspectable:", None, (BOOL,), False)
        c.send(self.window, "setContentView:", None, (PTR,), self.webview)
        c.send(self.window, "center", None)
        self._menu()
        c.send(self.window, "makeKeyAndOrderFront:", None, (PTR,), None)
        c.send(self.app, "activateIgnoringOtherApps:", None, (BOOL,), True)
        self.timer = c.send(c.cls("NSTimer"),
            "scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:", PTR,
            (C.c_double, PTR, PTR, PTR, BOOL), 0.1, self.delegate, c.sel("tick:"), None, True)
        c.send(self.timer, "retain")
        url = c.send(c.cls("NSURL"), "URLWithString:", PTR, (PTR,), c.string(self.url))
        request = c.send(c.cls("NSURLRequest"), "requestWithURL:", PTR, (PTR,), url)
        c.send(self.webview, "loadRequest:", PTR, (PTR,), request)

    def _smoke_probe(self):
        self.smoke_requested = True
        c = self.cocoa
        code = smoke_probe_script()
        block = c.completion_block(self._smoke_done, self.fail)
        c.send(self.webview, "evaluateJavaScript:completionHandler:", None,
               (PTR, PTR), c.string(code), block)

    def _smoke_done(self, value, error):
        c = self.cocoa
        if error:
            message = c.python_string(c.send(error, "localizedDescription"))
            raise NativeHostError("Verifica della finestra macOS non riuscita: " + message)
        data = json.loads(c.python_string(value))
        if not smoke_ready(data):
            self.smoke_requested = False
            return
        if not data.get("bodyText") or not data.get("width") or not data.get("height"):
            raise NativeHostError("La finestra macOS non ha prodotto contenuto visibile.")
        data.update(status="passed", host="cocoa-wkwebview", nativeWebView=True)
        if self.screenshot_path:
            def snapshot_ready(image, error):
                if error or not image:
                    raise NativeHostError("Acquisizione della finestra macOS non riuscita.")
                tiff = c.send(image, "TIFFRepresentation")
                bitmap = c.send(c.cls("NSBitmapImageRep"), "imageRepWithData:", PTR, (PTR,), tiff)
                properties = c.send(c.cls("NSDictionary"), "dictionary")
                png = c.send(bitmap, "representationUsingType:properties:", PTR,
                             (NSUInteger, PTR), 4, properties)
                path = Path(self.screenshot_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                if not png or not c.send(png, "writeToFile:atomically:", BOOL,
                                         (PTR, BOOL), c.string(str(path)), True):
                    raise NativeHostError("Impossibile salvare l’immagine della finestra macOS.")
                data["screenshot"] = str(path)
                self._finish_smoke(data)
            configuration = c.allocate("WKSnapshotConfiguration")
            try:
                if c.send(configuration, "respondsToSelector:", BOOL, (PTR,),
                          c.sel("setAfterScreenUpdates:")):
                    c.send(configuration, "setAfterScreenUpdates:", None, (BOOL,), True)
                block = c.completion_block(snapshot_ready, self.fail)
                c.send(self.webview, "takeSnapshotWithConfiguration:completionHandler:", None,
                       (PTR, PTR), configuration, block)
            finally:
                c.send(configuration, "release", None)
        else:
            self._finish_smoke(data)

    def _finish_smoke(self, data):
        self.smoke_result = data
        if self.smoke_report:
            path = Path(self.smoke_report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.cocoa.send(self.window, "close", None)

    def alert(self, title, message, question=False):
        c = self.cocoa
        alert = c.allocate("NSAlert")
        try:
            c.send(alert, "setMessageText:", None, (PTR,), c.string(title))
            c.send(alert, "setInformativeText:", None, (PTR,), c.string(message))
            c.send(alert, "addButtonWithTitle:", PTR, (PTR,), c.string("Sì" if question else "OK"))
            if question:
                c.send(alert, "addButtonWithTitle:", PTR, (PTR,), c.string("No"))
            return c.send(alert, "runModal", NSInteger) == 1000
        finally:
            c.send(alert, "release", None)

    def dialog(self, kind, title, filters=None, multiple=False, suggested_name=""):
        c = self.cocoa
        save = kind == "save"
        panel = c.send(c.cls("NSSavePanel" if save else "NSOpenPanel"),
                       "savePanel" if save else "openPanel")
        c.send(panel, "setTitle:", None, (PTR,), c.string(title))
        c.send(panel, "setCanCreateDirectories:", None, (BOOL,), save or kind == "folder")
        if not save:
            c.send(panel, "setCanChooseDirectories:", None, (BOOL,), kind == "folder")
            c.send(panel, "setCanChooseFiles:", None, (BOOL,), kind != "folder")
            c.send(panel, "setAllowsMultipleSelection:", None, (BOOL,), multiple and kind != "folder")
        if suggested_name:
            c.send(panel, "setNameFieldStringValue:", None, (PTR,), c.string(suggested_name))
        extensions = filter_extensions(filters)
        if extensions and kind != "folder":
            array = c.send(c.cls("NSMutableArray"), "array")
            for extension in extensions:
                c.send(array, "addObject:", None, (PTR,), c.string(extension))
            c.send(panel, "setAllowedFileTypes:", None, (PTR,), array)
            c.send(panel, "setAllowsOtherFileTypes:", None, (BOOL,), False)
        if c.send(panel, "runModal", NSInteger) != 1:
            return []
        if save or kind == "folder" or not multiple:
            url = c.send(panel, "URL")
            return [c.python_string(c.send(url, "path"))] if url else []
        urls = c.send(panel, "URLs")
        count = c.send(urls, "count", NSUInteger)
        return [c.python_string(c.send(c.send(urls, "objectAtIndex:", PTR, (NSUInteger,), i), "path"))
                for i in range(count)]

    def run(self):
        c = self.cocoa
        try:
            self._create()
            c.send(self.app, "run", None)
            if self.error:
                raise NativeHostError(str(self.error)) from self.error
            return 0
        finally:
            self._close_tasks()
            if self.timer:
                c.send(self.timer, "invalidate", None)
                c.send(self.timer, "release", None)
            if self.webview:
                c.send(self.webview, "setNavigationDelegate:", None, (PTR,), None)
                c.send(self.webview, "setUIDelegate:", None, (PTR,), None)
                c.send(self.webview, "stopLoading", None)
                c.send(self.webview, "release", None)
            if self.window:
                c.send(self.window, "setDelegate:", None, (PTR,), None)
                c.send(self.window, "close", None)
                c.send(self.window, "release", None)
            if self.delegate:
                c.send(self.delegate, "release", None)
            c.send(self.pool, "drain", None)


def filter_extensions(filters) -> list[str]:
    """Convert the shared native-dialog schema to AppKit filename extensions."""
    if not filters:
        return []
    extensions = []
    for _label, pattern in normalize_filters(filters):
        for part in pattern.split(";"):
            part = part.strip()
            if part in ("*", "*.*"):
                return []
            extension = part.removeprefix("*.").lstrip(".")
            if extension and not any(char in extension for char in "*/\\?\0"):
                extensions.append(extension)
    return list(dict.fromkeys(extensions))


def _ui_call(function):
    if not _active_host:
        raise NativeHostError("La finestra desktop non è aperta.")
    return _active_host.invoke(function)


def pick_files(title="Seleziona i file", filters=None, multiple=True) -> list[str]:
    return _ui_call(lambda: _active_host.dialog("open", title, filters, multiple))


def pick_directory(title="Seleziona una cartella") -> str | None:
    paths = _ui_call(lambda: _active_host.dialog("folder", title))
    return paths[0] if paths else None


def save_file(title="Salva file", suggested_name="", filters=None) -> str | None:
    paths = _ui_call(lambda: _active_host.dialog("save", title, filters, False, suggested_name))
    return paths[0] if paths else None


def _alert(title, message, question=False):
    if _active_host:
        return _ui_call(lambda: _active_host.alert(title, message, question))
    c = _Cocoa()
    pool = c.allocate("NSAutoreleasePool")
    alert = None
    try:
        app = c.send(c.cls("NSApplication"), "sharedApplication")
        c.send(app, "setActivationPolicy:", BOOL, (NSInteger,), 0)
        c.send(app, "activateIgnoringOtherApps:", None, (BOOL,), True)
        alert = c.allocate("NSAlert")
        c.send(alert, "setMessageText:", None, (PTR,), c.string(title))
        c.send(alert, "setInformativeText:", None, (PTR,), c.string(message))
        c.send(alert, "addButtonWithTitle:", PTR, (PTR,), c.string("Sì" if question else "OK"))
        if question:
            c.send(alert, "addButtonWithTitle:", PTR, (PTR,), c.string("No"))
        return c.send(alert, "runModal", NSInteger) == 1000
    finally:
        if alert:
            c.send(alert, "release", None)
        c.send(pool, "drain", None)


def notify(title: str, message: str) -> None:
    _alert(title, message)


def confirm(title: str, message: str | None = None) -> bool:
    if message is None:
        title, message = "NewPat", title
    return bool(_alert(title, message, True))


def request_close() -> bool:
    return bool(_active_host and _ui_call(_active_host.request_close))


def run_window(url: str, title: str = "NewPat", on_close=None, *, smoke_test=False,
               smoke_report=None, user_data_dir=None, timeout=60, screenshot_path=None, **_ignored) -> int:
    """Run the Cocoa window on the process main thread, without opening Safari.

    The WKWebView data store is nonpersistent; durable application data belongs
    to the supplied NIPAT service, not to a WebKit cache or browser profile.
    """
    global _active_host
    if sys.platform != "darwin":
        raise NativeHostError("Questo componente desktop richiede macOS.")
    if _active_host:
        raise NativeHostError("Una finestra NewPat è già aperta in questo processo.")
    host = _Window(url, title, on_close, smoke_test, smoke_report, timeout, screenshot_path)
    _active_host = host
    try:
        return host.run()
    finally:
        _active_host = None
