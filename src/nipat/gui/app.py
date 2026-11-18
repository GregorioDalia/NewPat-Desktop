"""Desktop GUI entrypoint and narrowly scoped native file operations."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import zipfile

from nipat import __version__
from nipat.branding import PRODUCT_NAME
from nipat.errors import ValidationError
from .host import native_host
from .server import DesktopServer
from .service import GuiService


class DesktopApplication:
    def __init__(self, layout=None, *, host=None, service=None, assets=None):
        self.host = host or native_host()
        self.service = service or GuiService(layout)
        self.server = DesktopServer(self.call, assets=assets)

    def dialog(self, params):
        title = str(params.get("title") or "Seleziona file")[:200]
        if params.get("directory"):
            result = self.host.pick_directory(title)
            return {"paths": [str(result)] if result else []}
        if params.get("save"):
            result = self.host.save_file(title, str(params.get("suggested_name") or ""), params.get("filters"))
            return {"paths": [str(result)] if result else []}
        result = self.host.pick_files(title, params.get("filters"), bool(params.get("multiple", False)))
        if isinstance(result, (str, Path)):
            result = [result]
        return {"paths": [str(p) for p in result or []]}

    def _result_file(self, params):
        return self.service._results().file_path(params["run_id"], params["file_id"])

    def file_url(self, params):
        path = self._result_file(params)
        # Only non-executable media can be embedded. Original HTML/SVG is an
        # attachment, preventing another document from acquiring desktop RPC.
        safe = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".txt": "text/plain; charset=utf-8",
                ".csv": "text/plain; charset=utf-8", ".tsv": "text/plain; charset=utf-8",
                ".json": "application/json; charset=utf-8", ".log": "text/plain; charset=utf-8"}
        return self.server.register(path, mime=safe.get(path.suffix.lower(), "application/octet-stream"),
                                    attachment=path.suffix.lower() not in safe)

    def export_file(self, params):
        path = self._result_file(params)
        destination = self.host.save_file("Salva il file originale", path.name, None)
        if not destination:
            return {"cancelled": True}
        destination = Path(destination).expanduser().resolve()
        if destination == path.resolve():
            raise ValidationError("Scegli una destinazione diversa dal file originale.")
        # The native Save dialog requests overwrite confirmation.
        shutil.copyfile(path, destination)
        return {"path": str(destination), "name": destination.name}

    def export_run(self, params):
        store = self.service._results()
        run_id = params["run_id"]
        files = store.files(run_id)
        name = PRODUCT_NAME + "_" + re.sub(r"[^\w.-]+", "_", run_id) + "_risultati.zip"
        destination = self.host.save_file("Salva i risultati dell’esperimento", name,
                                          [{"name": "Archivio ZIP", "extensions": ["zip"]}])
        if not destination:
            return {"cancelled": True}
        destination = Path(destination).expanduser().resolve()
        paths = [(store.file_path(run_id, f["id"]), f["relative_path"]) for f in files]
        if any(destination == p.resolve() for p, _ in paths):
            raise ValidationError("Non sovrascrivere un file dell’esperimento originale.")
        # Publish the archive only after every scoped original has been copied.
        import tempfile
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".zip", delete=False) as out:
                temporary = Path(out.name)
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path, relative in paths:
                    archive.write(path, relative)
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return {"path": str(destination), "files": len(paths)}

    def open_run_directory(self, params):
        from .diagnostics import open_directory

        if set(params) != {"run_id"}:
            raise ValidationError("Seleziona un esperimento per aprirne la cartella.")
        directory = self.service._results()._run(params["run_id"])
        open_directory(directory)
        return {"opened": True}

    def export_diagnostics(self, params):
        from datetime import datetime
        from .diagnostics import write_bundle

        if set(params) - {"run_id"}:
            raise ValidationError("Richiesta diagnostica non valida.")
        run_dir = None
        if "run_id" in params:
            run_dir = self.service._results()._run(params["run_id"])
        destination = self.host.save_file(
            "Salva la diagnostica · log e informazioni sull’ambiente",
            f"{PRODUCT_NAME}-diagnostica-{datetime.now():%Y%m%d-%H%M%S}.zip",
            [{"name": "Archivio ZIP", "extensions": ["zip"]}],
        )
        if not destination:
            return {"cancelled": True}
        # Also work when invalid preferences or an unavailable runtime prevented
        # the experiment from reaching its first step.
        try:
            layout = self.service.layout
        except Exception:
            layout = self.service.base_layout
        try:
            resources = self.service.resources_get()
        except Exception as exc:
            resources = {"status": "unavailable", "error": str(exc)}
        return write_bundle(Path(destination), layout, resources=resources, run_dir=run_dir)

    @staticmethod
    def _local_file(value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Seleziona {label}.")
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
            raise ValidationError("IGV utilizza file locali; seleziona il file sul computer.")
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValidationError(f"Il percorso di {label} non è un file.")
        return path

    def prepare_igv(self, params):
        from .igv import LocalIGV
        ui = self.service.ui_get() if hasattr(self.service, "ui_get") else {}
        return LocalIGV(self.server.register, language=ui.get("language", "it")).prepare(params)

    def save_igv_session(self, params):
        session = params.get("session")
        if not isinstance(session, dict):
            raise ValidationError("Sessione IGV non valida.")
        # Export durable local selections, not expired per-process capabilities.
        encoded = json.dumps(session, ensure_ascii=False, allow_nan=False, indent=2)
        if self.server.token in encoded or re.search(r'https?://', encoded, flags=re.I):
            raise ValidationError("La sessione deve contenere percorsi locali, non URL temporanei.")
        destination = self.host.save_file("Salva la sessione IGV", f"{PRODUCT_NAME}_IGV_sessione.json",
                                          [{"name": "Sessione JSON", "extensions": ["json"]}])
        if not destination:
            return {"cancelled": True}
        Path(destination).write_text(encoded + "\n", encoding="utf-8")
        return {"path": str(destination)}

    def call(self, method, params):
        callbacks = {"dialog.open": self.dialog, "dialog.directory": lambda p: self.dialog({**p, "directory": True}),
                     "files.url": self.file_url, "files.open": self.file_url, "files.export": self.export_file,
                     "runs.export": self.export_run, "igv.prepare": self.prepare_igv,
                     "runs.open_directory": self.open_run_directory,
                     "diagnostics.export": self.export_diagnostics,
                     "igv.session.save": self.save_igv_session,
                     "app.close": lambda _p: (self.host.request_close(), {"closing": True})[1]}
        if method in callbacks:
            return callbacks[method](params)
        return self.service.call(method, params)

    def on_close(self):
        status = self.service.call("close_status")
        if not status["active"]:
            return True
        if not self.host.confirm("Analisi in corso", f"Vuoi interrompere le analisi prima di chiudere {PRODUCT_NAME}?"):
            return False
        for job in status["jobs"]:
            self.service.call("jobs.cancel", {"job_id": job["id"]})
        if self.service.call("close_status")["active"]:
            self.host.notify("Interruzione richiesta", f"Attendi la conclusione dell’interruzione nella schermata Attività, poi chiudi {PRODUCT_NAME}.")
            return False
        return True

    def run(self, *, smoke_test=False, smoke_report=None, timeout=60, smoke_screenshot=None):
        layout = self.service.layout
        log_dir = layout.workspace_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_dir / "gui.log", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger = logging.getLogger("nipat.gui")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            with self.server:
                return self.host.run_window(self.server.url, title=f"{PRODUCT_NAME} {__version__}",
                                            on_close=self.on_close,
                                            user_data_dir=layout.workspace_dir / ".gui" / "webview",
                                            smoke_test=smoke_test, smoke_report=smoke_report, timeout=timeout,
                                            screenshot_path=smoke_screenshot)
        finally:
            logger.removeHandler(handler)
            handler.close()


def main(layout=None, *, smoke_test=False, smoke_report=None, timeout=60, smoke_screenshot=None):
    try:
        return DesktopApplication(layout).run(smoke_test=smoke_test, smoke_report=smoke_report,
                                              timeout=timeout, smoke_screenshot=smoke_screenshot)
    except Exception as exc:
        logging.getLogger(__name__).exception("Desktop startup failed")
        if smoke_test:
            if smoke_report:
                output = Path(smoke_report)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps({"status": "failed", "appReady": False, "error": str(exc)},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"{PRODUCT_NAME} native GUI smoke failed: {exc}", file=sys.stderr)
            return 1
        try:
            native_host().notify(f"{PRODUCT_NAME} · avvio non riuscito", str(exc))
        except Exception:
            print(f"{PRODUCT_NAME}: {exc}", file=sys.stderr)
        return 1
