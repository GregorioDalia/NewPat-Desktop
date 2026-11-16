"""Native GTK/WebKit desktop host on Ubuntu; no external browser fallback."""
from __future__ import annotations

import json
from pathlib import Path
import threading
from .windows_host import allowed_navigation as _allowed_navigation

_state = {}


def _libraries():
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        gi.require_version("WebKit2", "4.1")
        from gi.repository import GLib, Gtk, WebKit2
        return GLib, Gtk, WebKit2
    except (ImportError, ValueError) as exc:
        raise RuntimeError("La GUI richiede GTK 3 e WebKit2GTK 4.1. Ripristina il pacchetto NewPat tramite APT.") from exc


def _dispatch(function):
    if not _state or threading.get_ident() == _state.get("thread"):
        return function()
    done = threading.Event()
    result = {}

    def invoke():
        try:
            result["value"] = function()
        except Exception as exc:
            result["error"] = exc
        finally:
            done.set()
        return False
    _state["glib"].idle_add(invoke)
    if not done.wait(600):
        raise RuntimeError("La finestra di selezione non ha risposto.")
    if "error" in result:
        raise result["error"]
    return result.get("value")


def allowed_navigation(url, base):
    return _allowed_navigation(base, url)


def run_window(url, title="NewPat", on_close=None, *, smoke_test=False, smoke_report=None,
               user_data_dir=None, timeout=60, screenshot_path=None, **_):
    GLib, Gtk, WebKit = _libraries()
    if not Gtk.init_check()[0]:
        raise RuntimeError("Impossibile aprire la finestra NewPat nella sessione grafica.")
    window = Gtk.Window(title=title)
    window.set_default_size(1440, 920)
    window.set_size_request(900, 650)
    manager = WebKit.WebsiteDataManager.new_ephemeral()
    context = WebKit.WebContext.new_with_website_data_manager(manager)
    view = WebKit.WebView.new_with_context(context)
    settings = view.get_settings()
    settings.set_enable_developer_extras(False)
    settings.set_enable_write_console_messages_to_stdout(False)
    settings.set_enable_html5_local_storage(True)
    _state.update(glib=GLib, gtk=Gtk, window=window, thread=threading.get_ident())
    result = {"code": 0, "completed": False, "pending": False, "closed": False}
    timers = []

    def close_request(*_args):
        if on_close and on_close() is False:
            return True
        return False

    def policy(_view, decision, kind):
        if kind in (WebKit.PolicyDecisionType.NAVIGATION_ACTION, WebKit.PolicyDecisionType.NEW_WINDOW_ACTION):
            if kind == WebKit.PolicyDecisionType.NEW_WINDOW_ACTION or not allowed_navigation(decision.get_request().get_uri(), url):
                decision.ignore()
                return True
        return False

    def fail(exc):
        result["code"] = 1
        if smoke_report:
            path = Path(smoke_report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"status": "failed", "appReady": False,
                                        "host": "gtk-webkit2", "error": str(exc)}, indent=2), encoding="utf-8")
        window.destroy()

    def complete(evidence):
        evidence.update(host="gtk-webkit2", nativeWebView=True, status="passed", window=True)
        if smoke_report:
            path = Path(smoke_report)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        result["completed"] = True
        window.destroy()

    def collect():
        if result["closed"] or result["completed"] or result["pending"]:
            return False
        result["pending"] = True
        code = "JSON.stringify({appReady:document.documentElement.dataset.nipatReady==='true'," \
               "title:document.title,readyState:document.readyState,bodyText:document.body.innerText.slice(0,2000)," \
               "width:innerWidth,height:innerHeight,userAgent:navigator.userAgent})"

        def received(web, task, *_args):
            if result["closed"]:
                return
            try:
                value = web.run_javascript_finish(task).get_js_value().to_string()
                evidence = json.loads(value)
                if not evidence.get("appReady"):
                    result["pending"] = False
                    timers.append(GLib.timeout_add(250, collect))
                    return
                if not evidence.get("bodyText") or "NewPat" not in evidence.get("title", ""):
                    raise RuntimeError("GUI non caricata")
                if screenshot_path:
                    import gi
                    gi.require_foreign("cairo")

                    def snapshot_ready(web, task, *_args):
                        try:
                            surface = web.get_snapshot_finish(task)
                            destination = Path(screenshot_path)
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            surface.write_to_png(str(destination))
                            evidence["screenshot"] = str(destination)
                            complete(evidence)
                        except Exception as exc:
                            fail(exc)
                    view.get_snapshot(WebKit.SnapshotRegion.VISIBLE, WebKit.SnapshotOptions.NONE,
                                      None, snapshot_ready, None)
                else:
                    complete(evidence)
            except Exception as exc:
                fail(exc)
        view.run_javascript(code, None, received, None)
        return False

    def finished(_view, event):
        if smoke_test and event == WebKit.LoadEvent.FINISHED and not result["pending"]:
            timers.append(GLib.timeout_add(200, collect))

    def expired():
        if smoke_test and not result["completed"] and not result["closed"]:
            fail(RuntimeError("La GUI non ha completato l’inizializzazione entro il tempo previsto."))
        return False

    def destroyed(*_args):
        result["closed"] = True
        Gtk.main_quit()

    window.connect("delete-event", close_request)
    window.connect("destroy", destroyed)
    view.connect("decide-policy", policy)
    view.connect("permission-request", lambda _v, request: (request.deny(), True)[1])
    view.connect("create", lambda *_: None)
    view.connect("load-changed", finished)
    window.add(view)
    window.show_all()
    view.load_uri(url)
    if smoke_test:
        timers.append(GLib.timeout_add_seconds(timeout, expired))
    try:
        Gtk.main()
    finally:
        for timer in timers:
            if GLib.MainContext.default().find_source_by_id(timer):
                GLib.source_remove(timer)
        _state.clear()
    return result["code"]


def request_close():
    if _state:
        _state["glib"].idle_add(lambda: (_state["window"].close(), False)[1] if _state else False)


def _dialog(title, filters=None, multiple=False, action="open", suggested_name=""):
    def choose():
        _, Gtk, _ = _libraries()
        modes = {"open": Gtk.FileChooserAction.OPEN, "save": Gtk.FileChooserAction.SAVE,
                 "directory": Gtk.FileChooserAction.SELECT_FOLDER}
        dialog = Gtk.FileChooserDialog(title=title, transient_for=_state.get("window"), action=modes[action])
        dialog.add_buttons("Annulla", Gtk.ResponseType.CANCEL, "Seleziona", Gtk.ResponseType.OK)
        dialog.set_select_multiple(bool(multiple and action == "open"))
        if action == "save":
            dialog.set_do_overwrite_confirmation(True)
            if suggested_name:
                dialog.set_current_name(Path(suggested_name).name)
        for spec in filters or []:
            item = Gtk.FileFilter()
            item.set_name(spec.get("name", "File"))
            for ext in spec.get("extensions", ["*"]):
                item.add_pattern("*" if ext == "*" else "*." + ext.lstrip("."))
            dialog.add_filter(item)
        try:
            return dialog.get_filenames() if dialog.run() == Gtk.ResponseType.OK else []
        finally:
            dialog.destroy()
    return _dispatch(choose)


def pick_files(title="Seleziona file", filters=None, multiple=True):
    return _dialog(title, filters, multiple)


def pick_directory(title="Seleziona cartella"):
    values = _dialog(title, action="directory")
    return values[0] if values else None


def save_file(title="Salva file", suggested_name="", filters=None):
    values = _dialog(title, filters, action="save", suggested_name=suggested_name)
    return values[0] if values else None


def _message(title, message, question=False):
    def show():
        _, Gtk, _ = _libraries()
        Gtk.init_check()
        dialog = Gtk.MessageDialog(transient_for=_state.get("window"), modal=True,
                                   message_type=Gtk.MessageType.QUESTION if question else Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.YES_NO if question else Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(message)
        try:
            return dialog.run() == Gtk.ResponseType.YES
        finally:
            dialog.destroy()
    return _dispatch(show)


def confirm(title, message):
    return _message(title, message, question=True)


def notify(title, message):
    _message(title, message)
