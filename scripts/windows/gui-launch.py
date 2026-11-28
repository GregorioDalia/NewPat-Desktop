"""Console-free entrypoint; environment/readiness are checked by run.ps1 first."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import traceback


def main() -> int:
    stream = None
    original = sys.stdout, sys.stderr
    log_path = Path(os.environ.get("NEWPAT_WORKSPACE_DIR", Path.home())) / "logs" / "gui-launch.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Each launch appends diagnostics; nothing is silently sent to a closed
        # pythonw console. This also gives CLI setup errors somewhere to print.
        stream = log_path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = stream
        print(f"\nNewPat desktop launch: {datetime.now().isoformat(timespec='seconds')}")
        from newpat.cli import main as cli_main
        code = cli_main(["gui"])
        if code:
            from newpat.desktop.windows_host import notify
            notify("NewPat · avvio non riuscito", f"NewPat non si è avviato correttamente.\nRegistro di avvio: {log_path}")
        return code
    except Exception as exc:
        if stream:
            traceback.print_exc(file=stream)
        try:
            from newpat.desktop.windows_host import notify
            notify("NewPat · avvio non riuscito", f"{exc}\n\nRegistro di avvio: {log_path}")
        except Exception:
            # Last resort still uses a built-in Windows dialog if application
            # imports themselves are damaged; no application DLL is needed.
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(exc), "NewPat - avvio non riuscito", 16)
        return 1
    finally:
        sys.stdout, sys.stderr = original
        if stream:
            stream.close()


if __name__ == "__main__":
    raise SystemExit(main())
