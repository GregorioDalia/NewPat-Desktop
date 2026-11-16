"""Private loopback transport for the embedded desktop window.

No browser is launched. Every asset, RPC and genomic byte range requires the
per-session capability, and mutating requests additionally require same-origin
JSON. Genomic resources are registered after a native selection, never exposed
as arbitrary filesystem paths in URLs.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import unquote, urlsplit

from nipat.errors import NipatError

MAX_RPC_BYTES = 2 * 1024 * 1024
CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; "
    "font-src 'self' data:; frame-src 'self' blob:; object-src 'none'; "
    "worker-src 'self' blob:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)


@dataclass(frozen=True)
class LocalResource:
    path: Path
    mime: str
    name: str
    attachment: bool = False


def _reject_nonfinite_json(value):
    raise ValueError("Non-finite JSON number: " + value)


def _validate_json_depth(value, maximum=64):
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > maximum:
            raise ValueError("JSON nesting exceeds the supported request structure")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)


def byte_range(value: str | None, size: int) -> tuple[int, int] | None:
    """Return an inclusive single byte range; reject malformed/unsatisfiable input."""
    if value is None:
        return None
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or size <= 0 or not any(match.groups()):
        raise ValueError("Invalid byte range")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("Invalid suffix range")
        return max(0, size - suffix), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable byte range")
    return start, end


class DesktopServer:
    def __init__(self, dispatcher, *, assets: Path | None = None):
        self.dispatcher = dispatcher
        self.assets = (assets or Path(__file__).with_name("web")).resolve()
        self.token = secrets.token_urlsafe(32)
        self.resources: dict[str, LocalResource] = {}
        self._resource_lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                # Request paths contain the session capability and must not be logged.
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(30)

            def _headers(self, code, mime, size, **extra):
                self.send_response(code)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(size))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Content-Security-Policy", CSP)
                if self.close_connection:
                    self.send_header("Connection", "close")
                for k, v in extra.items():
                    self.send_header(k.replace("_", "-"), str(v))
                self.end_headers()

            def _json(self, code, value):
                data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
                self._headers(code, "application/json; charset=utf-8", len(data))
                if self.command != "HEAD":
                    self.wfile.write(data)

            def _path(self):
                if self.headers.get("Host") != owner.host:
                    return None
                parsed = urlsplit(self.path)
                if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
                    return None
                prefix = "/" + owner.token + "/"
                if not parsed.path.startswith(prefix):
                    return None
                tail = unquote(parsed.path[len(prefix):])
                if "\\" in tail or "\x00" in tail or any(p in ("..", ".") for p in tail.split("/")):
                    return None
                return tail

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                route = self._path()
                if route is None:
                    self._json(404, {"error": "Not found"})
                    return
                if route == "health":
                    self._json(200, {"status": "ready", "application": "NIPAT"})
                    return
                if route.startswith("web/"):
                    relative = route[4:] or "index.html"
                    path = (owner.assets / relative).resolve()
                    if not path.is_relative_to(owner.assets) or not path.is_file():
                        self._json(404, {"error": "Not found"})
                        return
                    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                    if path.suffix == ".js":
                        mime = "text/javascript; charset=utf-8"
                    if path.suffix in {".html", ".css", ".json"}:
                        mime += "; charset=utf-8"
                    resource = LocalResource(path, mime, path.name)
                elif route.startswith("resources/"):
                    with owner._resource_lock:
                        resource = owner.resources.get(route[len("resources/"):])
                    if resource is None:
                        self._json(404, {"error": "Not found"})
                        return
                else:
                    self._json(404, {"error": "Not found"})
                    return
                try:
                    with resource.path.open("rb") as stream:
                        import os
                        info = os.fstat(stream.fileno())
                        size = info.st_size
                        try:
                            selected = byte_range(self.headers.get("Range"), size)
                        except ValueError:
                            self._headers(416, resource.mime, 0, Content_Range=f"bytes */{size}")
                            return
                        first, last = selected if selected else (0, size - 1)
                        length = max(0, last - first + 1)
                        extra = {"Accept_Ranges": "bytes"}
                        if selected:
                            extra["Content_Range"] = f"bytes {first}-{last}/{size}"
                        if resource.attachment:
                            from urllib.parse import quote
                            extra["Content_Disposition"] = "attachment; filename*=UTF-8''" + quote(resource.name)
                        self._headers(206 if selected else 200, resource.mime, length, **extra)
                        if self.command == "HEAD":
                            return
                        stream.seek(first)
                        while length:
                            chunk = stream.read(min(length, 256 * 1024))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            length -= len(chunk)
                except (FileNotFoundError, PermissionError, IsADirectoryError):
                    self._json(404, {"error": "File unavailable"})
                except (BrokenPipeError, ConnectionResetError, TimeoutError):
                    pass

            def do_POST(self):
                if self._path() != "api":
                    self.close_connection = True
                    self._json(404, {"error": "Not found"})
                    return
                if self.headers.get("Origin") != owner.origin:
                    self.close_connection = True
                    self._json(403, {"error": "Origin rejected"})
                    return
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    self.close_connection = True
                    self._json(415, {"error": "JSON required"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= MAX_RPC_BYTES:
                        self.close_connection = True
                        self._json(413, {"error": "Request too large"})
                        return
                    payload = json.loads(self.rfile.read(length), parse_constant=_reject_nonfinite_json)
                    _validate_json_depth(payload)
                    if not isinstance(payload, dict) or not isinstance(payload.get("method"), str):
                        raise ValueError("Invalid request")
                    params = payload.get("params", {})
                    if not isinstance(params, dict):
                        raise ValueError("Invalid parameters")
                    identifier = payload.get("id")
                    if identifier is not None and not isinstance(identifier, (str, int)):
                        raise ValueError("Invalid identifier")
                except (ValueError, UnicodeError, RecursionError):
                    self.close_connection = True
                    self._json(400, {"error": {"code": "invalid_request", "message": "Richiesta non valida."}})
                    return
                try:
                    result = owner.dispatcher(payload["method"], params)
                    self._json(200, {"id": identifier, "result": result})
                except (NipatError, ValueError, KeyError, OSError, RuntimeError) as exc:
                    self._json(200, {"id": identifier, "error": {"code": type(exc).__name__, "message": str(exc)}})
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception("Desktop operation failed: %s", payload["method"])
                    self._json(200, {"id": identifier, "error": {"code": "internal_error", "message": "Operazione non riuscita. Consulta il registro dell’applicazione."}})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.host = f"127.0.0.1:{self.httpd.server_port}"
        self.origin = "http://" + self.host
        self.base_url = self.origin + "/" + self.token + "/"
        self.url = self.base_url + "web/index.html"
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="NIPAT-local-ui", daemon=True)

    def register(self, path: Path | str, *, mime: str | None = None, attachment=False) -> dict:
        path = Path(path).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError("Seleziona un file, non una cartella.")
        file_id = secrets.token_urlsafe(24)
        guessed = mime or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with self._resource_lock:
            self.resources[file_id] = LocalResource(path, guessed, path.name, attachment)
        return {"url": self.base_url + "resources/" + file_id, "name": path.name,
                "mime": guessed, "size": path.stat().st_size}

    def start(self):
        self.thread.start()
        return self

    def close(self):
        if self.thread.is_alive():
            self.httpd.shutdown()
            self.thread.join(timeout=5)
        self.httpd.server_close()
        with self._resource_lock:
            self.resources.clear()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()
