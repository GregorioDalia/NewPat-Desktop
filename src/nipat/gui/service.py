"""Narrow JSON-RPC application facade for the native desktop window.

No RPC name is evaluated and no arbitrary command line is accepted. Platform
file dialogs and rendering are injected by the desktop host.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid

from nipat import __version__
from nipat.errors import ValidationError
from nipat.execution.options import ExecutionOptions
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.tracking import read_run_metadata
from nipat.gui.jobs import JobManager
from nipat.gui.plan import prepare_analysis
from nipat.paths import ProjectLayout
from nipat.preferences import Preferences, PreferencesStore
from nipat.resources import ResourceManager
from nipat.scientific_options import effective_config, migrate_saved_settings
from nipat_scientific.catalog import load_catalog
from nipat_scientific.settings import describe_settings


class GuiService:
    def __init__(self, base_layout: ProjectLayout | None = None, host: dict | None = None,
                 *, preferences_store=None, jobs=None, resource_factory=None,
                 results_factory=None, run_observer=None):
        self.base_layout = base_layout or ProjectLayout.discover()
        self.host = dict(host or {})
        self.preferences_store = preferences_store or PreferencesStore()
        self.jobs = jobs or JobManager()
        self.resource_factory = resource_factory or ResourceManager.from_environment
        self.results_factory = results_factory
        self._plans = OrderedDict()
        self._resource_previews = OrderedDict()
        self._update_offers = {}
        self._downloads = {}
        self._baseline = None
        self._results_key = None
        self._results_store = None
        self._lock = threading.RLock()
        from nipat.gui.lifecycle import RunObserver
        self.run_observer = run_observer or RunObserver(lambda: self.layout, self.jobs)

    @property
    def layout(self) -> ProjectLayout:
        return self.preferences_store.load().effective_layout(self.base_layout)

    def _results(self):
        key = (self.layout.runs_dir, self.ui_get()["language"],
               self.preferences_store.path.with_name("gui-imports.json"))
        from nipat.gui.results import ResultsStore
        with self._lock:
            if key != self._results_key:
                self._results_store = (self.results_factory(key[0]) if self.results_factory is not None
                                       else ResultsStore(key[0], language=key[1], registry_path=key[2],
                                                         status_observer=self.run_observer.observe))
                self._results_key = key
            return self._results_store

    def call(self, method: str, params: dict | None = None):
        if not isinstance(method, str) or (params is not None and not isinstance(params, dict)):
            raise ValidationError("Richiesta dell’interfaccia non valida.")
        params = params or {}
        handlers = {
            "bootstrap": self.bootstrap, "catalog.get": self.catalog,
            "preferences.get": self.preferences_get, "preferences.save": self.preferences_save,
            "ui.get": self.ui_get, "ui.save": self.ui_save,
            "plan.preview": self.plan_preview, "analysis.start": self.analysis_start,
            "jobs.list": self.jobs.list, "jobs.get": self.jobs.get, "jobs.logs": self.jobs.logs,
            "jobs.cancel": self.jobs.cancel, "jobs.active": self.jobs.active, "jobs.remove": self.job_remove,
            "jobs.result_id": self.job_result_id, "close_status": self.jobs.active, "run.reuse": self.run_reuse,
            "run.prepare": self.run_prepare, "runs.remove": self.run_remove,
            "run.igv": self.run_igv,
            "resources.get": self.resources_get, "resources.preview": self.resources_preview,
            "resources.apply": self.resources_apply, "environment.check": self.environment_check,
            "installation.get": self.installation_get,
            "installation.maintain": self.installation_maintain,
            "updates.check": self.updates_check, "updates.download": self.updates_download,
            "updates.install": self.updates_install, "updates.reveal": self.updates_reveal,
        }
        if method in handlers:
            return handlers[method](**params)
        result_methods = {"runs.list": "list_runs", "runs.get": "get_run",
                          "runs.files": "files", "runs.table": "table", "runs.curve": "curve",
                          "runs.overview": "overview", "runs.import": "register_run"}
        if method in result_methods:
            return getattr(self._results(), result_methods[method])(**params)
        if method in self.host:
            return self.host[method](deepcopy(params))
        raise KeyError(method)

    def bootstrap(self) -> dict:
        preferences = self.preferences_get()
        layout = Preferences.from_dict(preferences).effective_layout(self.base_layout)
        return {"version": __version__, "settings": {"schema_version": 1, "workflows": describe_settings()},
                "catalog": load_catalog(), "preferences": preferences,
                "scientific_settings": effective_config(preferences["scientific_settings"]),
                "layout": {"data_dir": str(layout.data_dir), "runs_dir": str(layout.runs_dir),
                           "project_dir": str(layout.project_dir)},
                "execution": ExecutionOptions(**preferences["execution"]).as_dict(),
                "ui": self.ui_get(), "jobs": self.jobs.list(include_logs=False)}

    def catalog(self) -> dict:
        return {"settings": {"schema_version": 1, "workflows": describe_settings()}, "catalog": load_catalog()}

    def preferences_get(self) -> dict:
        value = self.preferences_store.load()
        with self._lock:
            self._baseline = value
        return value.to_dict()

    def preferences_save(self, preferences: dict, baseline: dict | None = None) -> dict:
        value = Preferences.from_dict(preferences)
        with self._lock:
            original = Preferences.from_dict(baseline) if baseline is not None else self._baseline
        if original is None:
            raise ValidationError("Aprire le preferenze prima di salvarle.")
        if self.jobs.active()["active"] and (value.data_dir != original.data_dir
                                             or value.runs_dir != original.runs_dir):
            raise ValidationError("Attendere il completamento dell’analisi prima di cambiare le cartelle.")
        saved = self.preferences_store.save(
            value, baseline=original, validate=lambda p: p.effective_layout(self.base_layout))
        with self._lock:
            self._baseline = saved
        return saved.to_dict()

    def _ui_path(self) -> Path:
        return self.preferences_store.path.with_name("gui-preferences.json")

    def ui_get(self) -> dict:
        path = self._ui_path()
        defaults = {"language": "it", "reduce_motion": False}
        if not path.exists():
            return defaults
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValidationError("Preferenze dell’interfaccia non valide.")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValidationError("Impossibile leggere le preferenze dell’interfaccia.") from exc
        return self._validate_ui(value)

    @staticmethod
    def _validate_ui(value: dict) -> dict:
        if (not isinstance(value, dict) or set(value) != {"language", "reduce_motion"}
                or value.get("language") not in {"it", "en"}
                or type(value.get("reduce_motion")) is not bool):
            raise ValidationError("Scegliere italiano o inglese e una preferenza di movimento valida.")
        return dict(value)

    def ui_save(self, preferences: dict) -> dict:
        value = self._validate_ui(preferences)
        path = self._ui_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValidationError("Il file delle preferenze non deve essere un collegamento.")
        temporary = path.with_name(".gui-" + uuid.uuid4().hex + ".json")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return value

    def reference_catalog(self, language: str):
        from nipat.gui.references import ReferenceCatalog
        return ReferenceCatalog(self.preferences_store.path.with_name("references.json"), language=language)

    def plan_preview(self, draft: dict) -> dict:
        preferences = self.preferences_store.load()
        language = self.ui_get()["language"]
        prepared = prepare_analysis(draft, preferences.effective_layout(self.base_layout), preferences,
                                    language=language, reference_catalog=self.reference_catalog(language))
        token = uuid.uuid4().hex
        with self._lock:
            self._plans[token] = prepared
            while len(self._plans) > 10:
                self._plans.popitem(last=False)
        return {"preview_id": token, **deepcopy(prepared.preview)}

    def analysis_start(self, preview_id: str) -> dict:
        with self._lock:
            prepared = self._plans.pop(preview_id, None)
        if prepared is None:
            raise ValidationError("Il riepilogo non è più disponibile. Verificare di nuovo l’esperimento.")
        return self.jobs.start(prepared)

    def _derived_name(self, base, module=None):
        italian, english = {None: ("nuova analisi", "new analysis"), "contamination": ("contaminazione", "contamination"),
                            "cpi": ("CPI prenatale", "Prenatal CPI"), "cpin": ("CPI postnatale", "Postnatal CPI"),
                            "fetal-sex": ("sesso fetale", "fetal sex")}[module]
        suffix = " · " + (english if self.ui_get()["language"] == "en" else italian)
        # Generated names must fit the same 120-character field as typed names.
        return str(base)[:120 - len(suffix)].rstrip() + suffix

    @staticmethod
    def _requested_execution(metadata):
        admission = metadata.get("concurrent_execution")
        if isinstance(admission, dict) and isinstance(admission.get("requested_options"), dict):
            return admission["requested_options"]
        return metadata.get("execution_options", {})

    def run_reuse(self, run_id: str) -> dict:
        run = self._results().get_run(run_id)
        draft = run.get("draft")
        if draft is None:
            gui = run.get("gui") or {}
            draft = gui.get("draft")
        if isinstance(draft, dict):
            draft = deepcopy(draft)
            if "scientific_settings" in draft:
                draft["scientific_settings"] = migrate_saved_settings(draft["scientific_settings"])
            draft["name"] = self._derived_name(draft.get("name", run_id))
            return draft
        metadata = self._results().metadata(run_id)
        if metadata.get("workflow") == "fetal-sex":
            return self.run_prepare(run_id, "fetal-sex")
        if metadata.get("workflow") != "analysis":
            raise ValidationError("Per questo esperimento precedente creare una nuova analisi e selezionare i file. I risultati restano consultabili.")
        try:
            return self._draft_from_legacy(metadata)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError("La configurazione precedente non contiene tutti i collegamenti ai file. Creare un nuovo esperimento.") from exc

    def run_remove(self, run_id: str) -> dict:
        store = self._results()
        if store.forget_missing_import(run_id):
            return {"removed": True, "run_id": run_id, "outputs_preserved": True}
        path, metadata = store._metadata(run_id)
        finished = self.jobs.finished_for(path)
        if finished is None and not self.run_observer.inspect(path, metadata).get("can_remove"):
            english = self.ui_get()["language"] == "en"
            raise ValidationError("This experiment may still be active. Wait until its status can be verified before removing it from the list."
                                  if english else "L’esperimento potrebbe essere ancora attivo. Attendi che il suo stato sia verificabile prima di rimuoverlo dalla lista.")
        result = store.remove_run(run_id)
        if finished is not None:
            self.jobs.discard(finished)
        return result

    def job_result_id(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job["run_id"]:
            raise ValidationError("I risultati dell’esperimento non sono ancora disponibili.")
        path = Path(job["results_root"]) / job["run_id"]
        return {"run_id": self._results().session_run_id(path)}

    def job_remove(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job["finished_at"]:
            raise ValidationError("Attendere la fine dell’esperimento prima di rimuovere la scheda.")
        archive_id = None
        if job["run_id"]:
            # The session owns both paths. The archive preference may have changed
            # since this run finished, or a startup failure may predate run.json.
            path = Path(job["results_root"]) / job["run_id"]
            if (path / "run.json").is_file():
                store = self._results()
                archive_id = store.identifier_for_path(path)
                store.hide_path(path)
        self.jobs.discard(job_id)
        return {"removed": True, "run_id": job["run_id"], "archive_id": archive_id, "outputs_preserved": True}

    def run_igv(self, run_id: str, locus: str | None = None) -> dict:
        """Select recorded reference/BAM sources, preserving every original file."""
        reference, tracks = self._results().igv_sources(run_id)
        english = self.ui_get()["language"] == "en"
        if not reference.get("fasta") or not tracks:
            raise ValidationError("This experiment has no recorded FASTA reference and BAM inputs. Select the files in IGV."
                                  if english else "Questo esperimento non contiene i collegamenti a un riferimento FASTA e a file BAM. Seleziona i file nella pagina IGV.")
        if locus is not None and (not isinstance(locus, str) or len(locus) > 300
                or not re.fullmatch(r"[A-Za-z0-9_.-]+(?::[0-9,]+(?:-[0-9,]+)?)?", locus)):
            raise ValidationError("Invalid genomic coordinates." if english else "Coordinate genomiche non valide.")
        return {"reference": reference, "tracks": tracks, "locus": locus or "all"}

    def run_prepare(self, run_id: str, module: str) -> dict:
        """Prepare only one new consumer using recorded counts, never call again.

        Output identities come from the results adapter's validated artifact
        mapping. Imported count inputs retain their explicit biological IDs.
        Missing family roles/population resources stay empty for user selection.
        """
        if module not in {"contamination", "cpi", "cpin", "fetal-sex"}:
            raise ValidationError("Scegliere un modulo disponibile per le tabelle di conteggi.")
        store = self._results()
        run, metadata = store.get_run(run_id), store.metadata(run_id)
        parameters = metadata.get("parameters", {})
        source = run.get("draft")
        if not isinstance(source, dict):
            try:
                source = self._draft_from_legacy(metadata) if metadata.get("workflow") == "analysis" else {}
            except (KeyError, TypeError, ValueError):
                source = {}
        source = deepcopy(source)
        if module == "fetal-sex":
            # Generic DNP and SNP outputs do not identify the required chromosome roles.
            settings = source.get("scientific_settings", parameters.get("scientific_settings_effective", {}))
            recorded = parameters.get("fetal_sex") or {}
            fetal = source.get("fetal_sex") or {"id": recorded.get("sample_id", ""),
                                                **{role: recorded.get(role, "") for role in ("autosomes", "x", "y")}}
            return {"name": self._derived_name(run.get("name") or run_id, module),
                    "caller": "tables", "samples": [], "fetal_sex": fetal,
                    "scientific_settings": effective_config(migrate_saved_settings(settings)),
                    "execution": source.get("execution", self._requested_execution(metadata))}
        mapping = {row["sample_id"]: row.get("biological_id", row["sample_id"])
                   for row in parameters.get("sample_mapping", [])
                   if isinstance(row, dict) and isinstance(row.get("sample_id"), str)}
        successful = {step["id"] for step in run.get("steps", [])
                      if step.get("status") == "succeeded" and step.get("module") in {"dnp-call", "snp-call"}}
        samples = {}
        for marker, recorded_id, path in store.caller_count_tables(run_id, successful, mapping):
            identifier = mapping[recorded_id]
            if not identifier:
                continue
            key = (marker, identifier)
            if key in samples:
                raise ValidationError("Più tabelle corrispondono allo stesso campione. Selezionare esplicitamente i file in un nuovo esperimento.")
            samples[key] = {"id": identifier, "path": str(path), "kind": marker.lower() + "-table"}
        # A tables-only/mixed experiment may already contain original counts,
        # without any caller-owned output. These paths were recorded as inputs.
        evidence = {Path(item["path"]): item for item in metadata.get("inputs", [])
                    if isinstance(item, dict) and isinstance(item.get("path"), str)}
        for row in source.get("samples", []):
            if not isinstance(row, dict) or row.get("kind") not in {"dnp-table", "snp-table"}:
                continue
            marker, identifier = row["kind"][:3].upper(), row.get("id")
            path = Path(row.get("path", "")).expanduser()
            if not isinstance(identifier, str) or not path.is_absolute():
                continue
            store.require_count_table(path)
            path = path.resolve()
            key = (marker, identifier)
            if key in samples and Path(samples[key]["path"]) != path:
                raise ValidationError("Conteggi ambigui per un campione. Selezionare esplicitamente i file in un nuovo esperimento.")
            recorded = evidence.get(path, {})
            store.verify_count_table(path, recorded.get("sha256"), recorded.get("size_bytes"))
            samples[key] = {"id": identifier, "path": str(path), "kind": row["kind"]}
        if not samples:
            raise ValidationError("Non sono disponibili conteggi completi associati ai campioni. Creare un nuovo esperimento da tabelle esistenti e selezionare i file; i calcoli precedenti non saranno ripetuti.")
        markers = {marker for marker, _identifier in samples}
        resources = {"DNP": {}, "SNP": {}}
        for marker in markers:
            previous = source.get("resources", {}).get(marker, {})
            legacy_marker = "SNP" if str(metadata.get("workflow", "")).startswith("snp") else parameters.get("marker_type", "DNP")
            legacy = parameters if marker == legacy_marker else {}
            if module == "contamination":
                resources[marker] = {"contamination_panel": previous.get("contamination_panel") or previous.get("panel")
                                     or legacy.get("contamination_panel") or legacy.get("panel")}
            elif module == "cpi":
                resources[marker] = {"popfreq": previous.get("popfreq") or legacy.get("popfreq"),
                                     "cpi_cutoffs": previous.get("cpi_cutoffs", [])}
            else:
                resources[marker] = {"popfreq": previous.get("popfreq") or legacy.get("popfreq"),
                                     "cpin_panel": previous.get("cpin_panel")}
        families = {"cpi": [], "cpin": []}
        if module in families:
            roles = ("mother", "father") if module == "cpi" else ("mother", "father", "child")
            candidates = source.get("families", {}).get(module, [])
            if not candidates:
                candidates = [{"id": row.get("id"), **{role: mapping.get(row.get(role), row.get(role)) for role in roles}}
                              for row in run.get("families", []) if row.get("module") == module]
            for family in candidates:
                if (isinstance(family, dict) and isinstance(family.get("id"), str)
                        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}", family["id"])
                        and all((marker, family.get(role)) in samples for marker in markers for role in roles)
                        and len({family[role] for role in roles}) == len(roles)):
                    row = {"id": family["id"], **{role: family[role] for role in roles}}
                    if row not in families[module]:
                        families[module].append(row)
        settings = source.get("scientific_settings", parameters.get("scientific_settings_effective", {}))
        return {"name": self._derived_name(run.get("name") or run_id, module),
                "caller": "tables", "samples": list(samples.values()), "reference": None,
                "branches": {marker: [module] if marker in markers else [] for marker in ("DNP", "SNP")},
                "resources": resources, "families": families,
                "scientific_settings": effective_config(migrate_saved_settings(settings)),
                "execution": source.get("execution", self._requested_execution(metadata))}

    def _draft_from_legacy(self, metadata: dict) -> dict:
        p = metadata["parameters"]
        plan = p["plan"]
        mounts = {item["container_path"]: item["host_path"] for item in metadata["input_mounts"]}
        mapping = {item["sample_id"]: item for item in p["sample_mapping"]}
        samples = []
        for sample in plan["samples"]:
            row = mapping[sample["id"]]
            if not row.get("fetal_sex_role") or row.get("shared_fetal_sex_table"):
                samples.append({"id": row.get("biological_id", sample["id"]),
                                "path": row["original_path"], "kind": sample["kind"]})
        draft = {"name": self._derived_name(metadata.get("run_name", "NewPat")),
                 "caller": p["caller"], "samples": samples, "branches": p["analyses_by_marker"],
                 "resources": {"DNP": {}, "SNP": {}}, "families": {"cpi": [], "cpin": []},
                 "scientific_settings": migrate_saved_settings(p.get("scientific_settings_effective", {})),
                 "execution": self._requested_execution(metadata)}
        for step in plan["steps"]:
            workflow, inputs, parameters = step["workflow"], step["inputs"], step["parameters"]
            if workflow == "fetal-sex":
                recorded = p["fetal_sex"]
                draft["fetal_sex"] = {"id": recorded["sample_id"],
                                      **{role: recorded[role] for role in ("autosomes", "x", "y")}}
                continue
            marker = "DNP" if workflow == "dnp-call" else "SNP" if workflow == "snp-call" else parameters["marker_type"]
            resource = draft["resources"][marker]
            if workflow in {"dnp-call", "snp-call"}:
                resource["panel"] = mounts[inputs["panel"]]
                if inputs.get("reference"):
                    draft["reference"] = mounts[inputs["reference"]]
            elif workflow == "contamination":
                resource["contamination_panel"] = mounts[inputs["panel"]]
            elif workflow in {"cpi", "cpin"}:
                resource["popfreq"] = mounts[inputs["popfreq"]]
                if workflow == "cpi":
                    resource["cpi_cutoffs"] = [{"label": row["label"], "path": mounts[row["path"]]}
                                               for row in inputs.get("cutoffs", [])]
                elif inputs.get("markers"):
                    resource["cpin_panel"] = mounts[inputs["markers"]]
                for family in inputs["pairs" if workflow == "cpi" else "trios"]:
                    row = {"id": family["id"]}
                    for role in (("mother", "father") if workflow == "cpi" else ("mother", "father", "child")):
                        sid = family[role]["sample"]
                        row[role] = mapping.get(sid, {}).get("biological_id", sid)
                    if row not in draft["families"][workflow]:
                        draft["families"][workflow].append(row)
        return draft

    def resources_get(self) -> dict:
        preferences = self.preferences_store.load()
        return self.resource_factory(self.layout).snapshot(
            container_options=ExecutionOptions(**preferences.execution))

    def resources_preview(self, memory_mib: int, cpus: int) -> dict:
        manager = self.resource_factory(self.layout)
        change = manager.preview(memory_mib, cpus)
        token = uuid.uuid4().hex
        with self._lock:
            self._resource_previews[token] = (manager, change)
            while len(self._resource_previews) > 10:
                self._resource_previews.popitem(last=False)
        return {"preview_id": token, **change.as_dict()}

    def resources_apply(self, preview_id: str, confirmed: bool = False,
                        restart_confirmed: bool = False) -> dict:
        if self.jobs.active()["active"]:
            raise ValidationError("Attendere l’analisi prima di modificare le risorse.")
        with self._lock:
            selected = self._resource_previews.get(preview_id)
        if selected is None:
            raise ValidationError("Ripetere l’anteprima delle risorse prima di applicare la modifica.")
        manager, change = selected
        result = manager.apply(change, confirmed=confirmed, restart_confirmed=restart_confirmed)
        with self._lock:
            self._resource_previews.pop(preview_id, None)
        return result

    def environment_check(self, check_runtime: bool = True) -> dict:
        if type(check_runtime) is not bool:
            raise ValidationError("Verifica dell’ambiente non valida.")
        logs = []
        class CheckRunner(DockerComposeRunner):
            def _write(self, text, *, terminal=True, log=True):
                logs.extend(str(text).splitlines())
        runner = CheckRunner(self.layout)
        runner.doctor(check_runtime)
        return {"status": "passed", "runtime_checked": check_runtime, "logs": logs[-250:]}

    def installation_get(self) -> dict:
        from nipat.installation import installation_inventory
        return installation_inventory(self.layout.project_dir)

    def installation_maintain(self, operation: str, target: str,
                             confirmed: bool = False) -> dict:
        if confirmed is not True:
            raise ValidationError("Confermare l’operazione di manutenzione selezionata.")
        if self.jobs.active()["active"]:
            raise ValidationError("Attendere il termine dell’analisi prima della manutenzione.")
        from nipat.installation import start_maintenance
        path = start_maintenance(self.layout.project_dir, operation, target)
        return {"status": "handoff_started", "close_required": True, "record": str(path)}

    def updates_check(self, channel: str | None = None) -> dict:
        from nipat.updates import UpdateClient, detect_platform
        from nipat.update_handoff import windows_installation_platform
        channel = channel or self.preferences_store.load().update_channel
        if channel not in {"stable", "testing"}:
            raise ValidationError("Canale aggiornamenti non valido.")
        platform = detect_platform()
        if platform == "windows-x86_64":
            platform = windows_installation_platform(self.layout.project_dir)
        client = UpdateClient()
        result = client.check(__version__, channel, platform)
        output = asdict(result)
        if result.offer is not None:
            token = uuid.uuid4().hex
            with self._lock:
                self._update_offers = {token: (client, result.offer)}
            output["offer_id"] = token
        return output

    def updates_download(self, offer_id: str) -> dict:
        with self._lock:
            selected = self._update_offers.get(offer_id)
        if selected is None:
            raise ValidationError("Ripetere la ricerca degli aggiornamenti.")
        from nipat.update_handoff import update_cache_directory
        client, offer = selected
        downloaded = client.download(offer, update_cache_directory(self.layout.project_dir) / offer.version)
        with self._lock:
            self._downloads[offer_id] = downloaded
        return {"offer_id": offer_id, "status": "verified", "path": str(downloaded),
                "offer": asdict(offer)}

    def _downloaded_update(self, offer_id: str):
        with self._lock:
            selected, downloaded = self._update_offers.get(offer_id), self._downloads.get(offer_id)
        if selected is None or downloaded is None:
            raise ValidationError("Scaricare e verificare l’aggiornamento prima di installarlo.")
        return selected[1], downloaded

    def updates_reveal(self, offer_id: str) -> dict:
        offer, downloaded = self._downloaded_update(offer_id)
        if not offer.asset.platform.startswith("darwin-") or not downloaded.is_file():
            raise ValidationError("Il pacchetto macOS scaricato non è disponibile.")
        try:
            subprocess.run(["/usr/bin/open", "-R", str(downloaded)], check=True, timeout=15)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValidationError("Impossibile mostrare il pacchetto nel Finder.") from exc
        return {"status": "revealed"}

    def updates_install(self, offer_id: str, confirmed: bool = False) -> dict:
        if confirmed is not True:
            raise ValidationError("Confermare l’installazione dell’aggiornamento verificato.")
        offer, downloaded = self._downloaded_update(offer_id)
        if offer.asset.platform.startswith("darwin-"):
            return {"status": "manual_install", "path": str(downloaded), "close_required": False}
        if self.jobs.active()["active"]:
            raise ValidationError("Attendere il termine dell’analisi prima dell’aggiornamento.")
        from nipat.update_handoff import begin_update
        result = begin_update(offer, downloaded, self.layout.project_dir)
        return {"status": "handoff_started" if result else "not_started", "close_required": bool(result)}
