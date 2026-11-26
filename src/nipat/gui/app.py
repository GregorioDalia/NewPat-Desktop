"""Desktop GUI entrypoint and narrowly scoped native file operations."""
from __future__ import annotations

from contextlib import contextmanager
import base64
import binascii
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import webbrowser
import zipfile

from nipat import __version__
from nipat.branding import PRODUCT_NAME
from nipat.errors import ValidationError
from .host import native_host
from .reference_downloads import ReferenceDownloads
from .server import DesktopServer, MAX_RPC_BYTES
from .service import GuiService


@contextmanager
def _export_destination(destination: Path):
    """Expose only a complete export, including when replacing an existing file."""
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
        temporary = Path(out.name)
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


class DesktopApplication:
    def __init__(self, layout=None, *, host=None, service=None, assets=None):
        self.host = host or native_host()
        self.service = service or GuiService(layout)
        self.server = DesktopServer(self.call, assets=assets, pdf_export=self.save_report_stream)
        self.reference_downloads = ReferenceDownloads(lambda language: self.service.reference_catalog(language))

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
        store = self.service._results()
        run = store._run(params["run_id"])
        path = store.file_path(params["run_id"], params["file_id"])
        destination = self.host.save_file("Salva il file originale", path.name, None)
        if not destination:
            return {"cancelled": True}
        destination = Path(destination).expanduser().resolve()
        if destination.is_relative_to(run):
            raise ValidationError("Salva la copia fuori dalla cartella dell’esperimento originale.")
        # The native Save dialog requests overwrite confirmation.
        with _export_destination(destination) as temporary:
            shutil.copyfile(path, temporary)
        return {"path": str(destination), "name": destination.name}

    def export_run(self, params):
        store = self.service._results()
        run_id = params["run_id"]
        name = PRODUCT_NAME + "_" + re.sub(r"[^\w.-]+", "_", run_id) + "_results.zip"
        destination = self.host.save_file("Salva i risultati dell’esperimento", name,
                                          [{"name": "Archivio ZIP", "extensions": ["zip"]}])
        if not destination:
            return {"cancelled": True}
        destination = Path(destination).expanduser().resolve()
        if destination.is_relative_to(store._run(run_id)):
            raise ValidationError("Salva l’archivio fuori dalla cartella dell’esperimento originale.")
        paths = store.export_paths(run_id)
        with _export_destination(destination) as temporary:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path, relative in paths:
                    archive.write(path, relative)
        return {"path": str(destination), "files": len(paths)}

    def report_cases(self, params):
        from .analysis_report import report_case_options

        return report_case_options(self.service._results(), params["run_id"])

    def prepare_report(self, params):
        from .report_bundle import build_bundle, selected_ids

        kind = params.get("kind")
        if kind not in ("summary", "detailed", "combined"):
            raise ValidationError("Unknown report format.")
        store = self.service._results()
        ids = selected_ids(params, store.language == "en")
        bundle = build_bundle(store, params["run_id"], ids, kind)
        return bundle if "case_ids" in params or kind == "combined" else bundle["results"][0]

    def report_igv(self, params):
        from .report_bundle import selected_ids
        from .report_igv import report_igv_views

        store = self.service._results()
        case_ids = selected_ids(params, store.language == "en")
        views = report_igv_views(store, params["run_id"], case_ids, self.server.register)
        return {"views": views} if "case_ids" in params else views[case_ids[0]]

    def save_report(self, params):
        from .report_bundle import selected_ids

        english = params.get("language") == "en"
        ids = selected_ids(params, english)
        encoded = params.get("data_base64")
        invalid = "The PDF is incomplete." if english else "Il PDF è incompleto."
        if not isinstance(encoded, str) or len(encoded) > MAX_RPC_BYTES - 4096:
            raise ValidationError(invalid)
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValidationError(invalid) from error
        selection = ids[0] if len(ids) == 1 else "combined"
        return self.save_report_stream({**params, "selection": selection}, io.BytesIO(content))

    def save_report_stream(self, params, stream):
        """Save one complete PDF. Large requests arrive spooled to disk by the transport."""
        english = params.get("language") == "en"
        run_id, selection, kind = params["run_id"], params["selection"], params["kind"]
        if (kind not in ("summary", "detailed", "combined") or not isinstance(selection, str)
                or (selection != "combined" and not re.fullmatch(r"[0-9a-f]{64}", selection))):
            raise ValidationError("Invalid report selection." if english else "Selezione del rapporto non valida.")
        store = self.service._results()
        run = store._run(run_id)
        size = stream.seek(0, os.SEEK_END)
        stream.seek(max(0, size - 1024))
        has_end = stream.read().rstrip().endswith(b"%%EOF")
        stream.seek(0)
        if not has_end or stream.read(5) != b"%PDF-":
            raise ValidationError("The PDF is incomplete." if english else "Il PDF è incompleto.")
        stream.seek(0)
        run_label = re.sub(r"[^\w.-]+", "_", run_id)[:64]
        scope = selection[:12] if selection != "combined" else "selected"
        filename = f"NewPat_{run_label}_{scope}_{kind}.pdf"
        title = "Save the analysis report" if english else "Salva il rapporto di analisi"
        choice = self.host.save_file(title, filename, [{"name": "PDF", "extensions": ["pdf"]}])
        if not choice:
            return {"cancelled": True}
        destination = Path(choice).expanduser()
        if destination.suffix.lower() != ".pdf" or destination.is_symlink():
            raise ValidationError("Use a .pdf filename." if english else "Usa un nome con estensione .pdf.")
        destination = destination.resolve()
        if destination.is_relative_to(run) or destination.is_relative_to(store.root):
            raise ValidationError("Save the report outside the experiment archive." if english else
                                  "Salva il rapporto fuori dall’archivio degli esperimenti.")
        with _export_destination(destination) as temporary:
            with temporary.open("wb") as output:
                shutil.copyfileobj(stream, output, length=256 * 1024)
        return {"path": str(destination), "name": destination.name}

    def save_examples(self, params):
        from .examples import save_example_data

        if set(params) - {"language"}:
            raise ValidationError("Unexpected parameters for the example dataset.")
        language = params.get("language", "it")
        title = ("Choose a folder for the synthetic trio" if language == "en" else
                 "Scegli una cartella per il trio sintetico")
        parent = self.host.pick_directory(title)
        if not parent:
            return {"cancelled": True}
        target = save_example_data(self.service.base_layout.project_dir, Path(parent), language)
        return {"path": str(target)}

    def open_demo(self, params):
        from .examples import demo_draft

        if set(params) - {"language"}:
            raise ValidationError("Unexpected parameters for the example dataset.")
        return {"draft": demo_draft(self.service.base_layout, params.get("language", "it"))}

    def references_list(self, params):
        return self.service.reference_catalog(params.get("language", "it")).list()

    def references_register(self, params):
        language = params.get("language", "it")
        title = "Choose a local reference FASTA" if language == "en" else "Scegli un FASTA di riferimento locale"
        files = self.host.pick_files(title, [{"name": "FASTA", "extensions": ["fa", "fasta", "fna", "fas", "gz", "bgz", "bgzf"]}], False)
        if not files:
            return {"cancelled": True}
        path = files if isinstance(files, (str, Path)) else files[0]
        entry = self.service.reference_catalog(language).register(params.get("build"), path)
        return {"entry": entry}

    def references_resolve(self, params):
        entry = self.service.reference_catalog(params.get("language", "it")).resolve(params.get("id"))
        return {"entry": entry}

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
            f"{PRODUCT_NAME}-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.zip",
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

    @staticmethod
    def open_igv_guide(params):
        if params:
            raise ValidationError("Unexpected parameters for the IGV guide.")
        # The native browser receives only the public guide, never a viewer session or file.
        try:
            opened = webbrowser.open_new_tab("https://igv.org/doc/webapp/")
        except (OSError, webbrowser.Error):
            opened = False
        return {"opened": opened}

    def prepare_igv(self, params):
        from .igv import LocalIGV
        ui = self.service.ui_get() if hasattr(self.service, "ui_get") else {}
        return LocalIGV(self.server.register, language=ui.get("language", "it"),
                        register_reference=self.server.register).prepare(params)

    def save_igv_session(self, params):
        session = params.get("session")
        if not isinstance(session, dict):
            raise ValidationError("Sessione IGV non valida.")
        # Export durable local selections, not expired per-process capabilities.
        encoded = json.dumps(session, ensure_ascii=False, allow_nan=False, indent=2)
        if self.server.token in encoded or re.search(r'https?://', encoded, flags=re.I):
            raise ValidationError("La sessione deve contenere percorsi locali, non URL temporanei.")
        destination = self.host.save_file("Salva la sessione IGV", f"{PRODUCT_NAME}_IGV_session.json",
                                          [{"name": "Sessione JSON", "extensions": ["json"]}])
        if not destination:
            return {"cancelled": True}
        with _export_destination(Path(destination)) as temporary:
            temporary.write_text(encoded + "\n", encoding="utf-8")
        return {"path": str(destination)}

    def call(self, method, params):
        callbacks = {"dialog.open": self.dialog, "dialog.directory": lambda p: self.dialog({**p, "directory": True}),
                     "references.list": self.references_list, "references.register": self.references_register,
                     "references.resolve": self.references_resolve,
                     "references.download": lambda p: self.reference_downloads.call("start", p),
                     "references.download_status": lambda p: self.reference_downloads.call("status", p),
                     "references.download_cancel": lambda p: self.reference_downloads.call("cancel", p),
                     "files.url": self.file_url, "files.open": self.file_url, "files.export": self.export_file,
                     "runs.export": self.export_run, "igv.prepare": self.prepare_igv,
                     "reports.cases": self.report_cases, "reports.prepare": self.prepare_report,
                     "reports.save": self.save_report, "reports.igv": self.report_igv,
                     "runs.open_directory": self.open_run_directory,
                     "diagnostics.export": self.export_diagnostics, "examples.save": self.save_examples,
                     "examples.demo": self.open_demo,
                     "igv.about": self.open_igv_guide, "igv.session.save": self.save_igv_session,
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
            self.reference_downloads.close()
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
