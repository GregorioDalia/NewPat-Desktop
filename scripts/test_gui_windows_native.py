"""Exercise a real HWND/WebView2 control on the Windows CI desktop.

This check uses no scientific engine and opens no external browser. The report
is produced only after JavaScript executes in Microsoft's embedded control.
"""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import tempfile
import threading

from newpat.desktop.windows_host import run_window


def main(run_native_window=run_window, expected_host="win32-webview2"):
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--url")
    parser.add_argument("--screenshot", type=Path)
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()
    token = secrets.token_urlsafe(32)
    body = ("<!doctype html><html><head><meta charset=utf-8><title>NIPAT native smoke</title>"
            "</head><body><main id=app>NIPAT desktop · native embedded view</main>"
            "<script>document.documentElement.dataset.nipatReady='true'</script></body></html>").encode()

    class Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != f"/{token}/web/index.html":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = None
    try:
        url = args.url
        if not url:
            server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{server.server_port}/{token}/web/index.html"
        with tempfile.TemporaryDirectory(prefix="nipat-webview2-smoke-", ignore_cleanup_errors=True) as profile:
            run_native_window(url, title="NIPAT native desktop smoke", smoke_test=True,
                       smoke_report=args.report, timeout=args.timeout, user_data_dir=profile,
                       screenshot_path=args.screenshot)
        data = json.loads(args.report.read_text(encoding="utf-8"))
        assert data["status"] == "passed" and data["nativeWebView"] and data["appReady"]
        assert data["host"] == expected_host and "AppleWebKit" in data["userAgent"]
        assert data["width"] > 0 and data["height"] > 0
        if args.screenshot:
            assert args.screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        if not args.url:
            assert "NIPAT desktop" in data["bodyText"]
        print(json.dumps({"status": "passed", "host": data["host"],
                          "runtime_version": data.get("runtime_version", "system WKWebView")}))
    finally:
        if server:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
