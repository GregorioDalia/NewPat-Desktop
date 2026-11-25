import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from nipat.cli import build_parser
from nipat.gui import app, linux_host, macos_host, windows_host
from nipat.gui.host import smoke_ready


def test_full_application_smoke_cli_accepts_screenshot():
    args = build_parser().parse_args([
        "gui", "--smoke-test", "--smoke-report", "report.json",
        "--smoke-screenshot", "window.png", "--smoke-timeout", "90",
    ])
    assert args.smoke_test is True
    assert args.smoke_report == Path("report.json")
    assert args.smoke_screenshot == Path("window.png")
    assert args.smoke_timeout == 90


def test_application_forwards_native_smoke_and_screenshot(tmp_path, monkeypatch):
    seen = {}
    class Server:
        url = "http://127.0.0.1:5678/capability/web/index.html"
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def native_run(url, **options):
        seen.update(url=url, **options)
        return 0
    monkeypatch.setattr(app, "DesktopServer", lambda dispatcher, *, assets, pdf_export: Server())
    application = app.DesktopApplication(
        host=SimpleNamespace(run_window=native_run),
        service=SimpleNamespace(layout=SimpleNamespace(workspace_dir=tmp_path)),
    )
    report, screenshot = tmp_path / "native.json", tmp_path / "native.png"
    assert application.run(smoke_test=True, smoke_report=report, smoke_screenshot=screenshot, timeout=90) == 0
    assert seen["smoke_test"] is True and seen["smoke_report"] == report
    assert seen["screenshot_path"] == screenshot and seen["timeout"] == 90


def test_ci_failure_is_noninteractive_and_records_reason(tmp_path, monkeypatch):
    def fail(_layout): raise RuntimeError("Native runtime unavailable")
    monkeypatch.setattr(app, "DesktopApplication", fail)
    monkeypatch.setattr(app, "native_host", lambda: (_ for _ in ()).throw(AssertionError("Modal must not open in CI")))
    report = tmp_path / "native.json"
    assert app.main(smoke_test=True, smoke_report=report) == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "failed" and data["appReady"] is False
    assert data["error"] == "Native runtime unavailable"


def test_native_hosts_wait_for_successful_frontend_bootstrap():
    window = windows_host._Window.__new__(windows_host._Window)
    window.smoke_requested = True
    window._smoke_done(0, json.dumps(json.dumps({"appReady": False, "bodyText": "Loading"})))
    assert window.smoke_requested is False
    mac = macos_host._Window.__new__(macos_host._Window)
    mac.cocoa = SimpleNamespace(python_string=lambda _: json.dumps({"appReady": False, "bodyText": "Loading"}))
    mac.smoke_requested = True
    mac._smoke_done(1, None)
    assert mac.smoke_requested is False


def test_gtk_navigation_matches_other_native_hosts():
    base = "http://127.0.0.1:5678/capability/web/index.html"
    assert linux_host.allowed_navigation("http://127.0.0.1:5678/capability/files/token", base)
    assert not linux_host.allowed_navigation("http://127.0.0.1:5678/capability/%2e%2e/private", base)


def test_native_smoke_waits_for_pdf_generation_and_reports_render_failure():
    assert not smoke_ready({"appReady": True, "pdfExport": "pending"})
    assert smoke_ready({"appReady": True, "pdfExport": "passed"})
    with pytest.raises(RuntimeError, match="Incomplete PDF"):
        smoke_ready({"appReady": True, "pdfExport": "failed", "pdfError": "Incomplete PDF"})
