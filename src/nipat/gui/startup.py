"""A visible native preparation window while packaged launchers prepare runtime."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from nipat.processes import background_process_options


@contextmanager
def preparation_notice(app: Path, title="Preparazione NewPat", message="Preparazione dell’ambiente scientifico. Attendi il completamento."):
    code = ("import sys; sys.path.insert(0,sys.argv.pop(1)); "
            "from nipat.gui.startup import main; raise SystemExit(main())")
    process = subprocess.Popen([sys.executable, "-I", "-B", "-c", code, str(Path(app)/"src"),
                                "progress", title, message], stdin=subprocess.PIPE,
                                **background_process_options())
    try:
        yield
    finally:
        if process.stdin:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)


def show_startup_error(app: Path, message: str):
    code = ("import sys; sys.path.insert(0,sys.argv.pop(1)); "
            "from nipat.gui.startup import main; raise SystemExit(main())")
    subprocess.run([sys.executable, "-I", "-B", "-c", code, str(Path(app)/"src"), "error", "NewPat", str(message)], check=False,
                   **background_process_options())


def main():
    import html
    import time
    from .host import native_host
    from .server import DesktopServer
    action, title, message = sys.argv[1:4]
    host = native_host()
    if action == "error":
        host.notify(title, message)
        return 0
    finished = threading.Event()
    def read_end():
        sys.stdin.buffer.read()
        finished.set()
        # Native view initialization is asynchronous; retry until main() exits.
        while True:
            host.request_close()
            time.sleep(.1)
    threading.Thread(target=read_end, name="NIPAT-preparation-control", daemon=True).start()
    with tempfile.TemporaryDirectory(prefix="nipat-startup-") as directory:
        assets = Path(directory)
        shutil.copyfile(Path(__file__).with_name("web") / "newpat-wordmark.svg", assets / "newpat-wordmark.svg")
        content = """<!doctype html><html lang="it"><meta charset="utf-8"><title>NewPat</title><style>
        body{font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;background:#f6f7f8;color:#26342f;margin:0;display:grid;place-items:center;height:100vh}
        main{max-width:680px;padding:32px}h1{font-size:28px;font-weight:600}progress{width:100%;accent-color:#2f6b5b;margin-top:24px}
        small{color:#64706b} </style><main><img src="newpat-wordmark.svg" alt="NewPat" width="142" height="33"><h1>""" + html.escape(title) + "</h1><p>" + html.escape(message) + "</p><progress aria-label=\"Preparazione\"></progress><p><small>Il primo avvio può richiedere alcuni minuti. Il calcolo dei campioni non è ancora iniziato.</small></p></main></html>"
        (assets / "index.html").write_text(content, encoding="utf-8")
        with DesktopServer(lambda *_: None, assets=assets) as server:
            if finished.is_set():
                return 0
            return host.run_window(server.url, title=title, on_close=lambda: finished.is_set())


if __name__ == "__main__":
    raise SystemExit(main())
