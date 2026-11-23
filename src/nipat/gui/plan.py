"""Convert the desktop form into the existing, validated scientific plan.

The GUI owns presentation names only. All scientific validation and execution
remain in the same adapters used by the CLI.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nipat.errors import ValidationError
from nipat.execution.analysis_plan import build_analysis_plan
from nipat.execution.options import ExecutionOptions
from nipat.execution.tracking import input_stat_snapshot
from nipat.gui.igv import LocalIGV
from nipat.paths import ProjectLayout
from nipat.preferences import Preferences
from nipat.scientific_options import effective_config, normalize_config
from nipat_scientific.panels import read_dnp_list, read_snp_positions
from nipat_scientific.plan import validate_plan

_DRAFT_FIELDS = {"name", "caller", "samples", "branches", "reference", "resources",
                 "families", "scientific_settings", "execution", "reference_id", "reference_genome"}
_RESOURCE_FIELDS = {"panel", "popfreq", "contamination_panel", "cpi_cutoffs", "cpin_panel"}
_KINDS = {"bam": "samples", "snp-pileup": "pileups", "dnp-table": "dnp_tables",
          "snp-table": "snp_tables"}


def _object(value: Any, label: str, allowed: set[str] | None = None) -> dict:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValidationError(f"{label}: configurazione non valida.")
    if allowed is not None and set(value) - allowed:
        raise ValidationError(f"{label}: sono presenti opzioni non riconosciute.")
    return value


def _text(value: Any, label: str, *, maximum: int = 8192) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any(ord(c) < 32 for c in value)):
        raise ValidationError(f"{label}: inserire un valore valido.")
    return value.strip()


def _path(value: Any, label: str) -> Path | None:
    if value in (None, ""):
        return None
    raw = _text(value, label)
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise ValidationError(f"{label}: selezionare un percorso assoluto.")
    return path.resolve()


def _rows(value: Any, label: str, maximum: int = 10000) -> list:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValidationError(f"{label}: elenco non valido o troppo grande.")
    return value


@dataclass(frozen=True)
class PreparedAnalysis:
    draft: dict
    inputs: dict
    layout: ProjectLayout
    scientific_settings: dict
    execution: ExecutionOptions
    preview: dict
    evidence: tuple[tuple[Path, dict[str, int]], ...]
    language: str = "it"

    def assert_inputs_unchanged(self) -> None:
        for path, expected in self.evidence:
            try:
                current = input_stat_snapshot(path.stat())
            except OSError as exc:
                filename = path.name
                message = (f"Input unavailable. Check the file {filename}." if self.language == "en"
                           else f"Input non disponibile. Controlla il file {filename}.")
                raise ValidationError(message) from exc
            if current != expected:
                filename = path.name
                message = (f"The file {filename} has changed. Review it before retrying." if self.language == "en"
                           else f"Il file {filename} è cambiato. Controllalo prima di riprovare.")
                raise ValidationError(message)


def _check_named_reference(entry, inputs, caller, language):
    checker = LocalIGV(None, language=language)
    fasta, fai = Path(entry["fasta"]), Path(entry["index"])
    chromosomes = checker.fasta_index(fasta, fai, expected_sha256=entry["index_sha256"])
    lengths = {item["name"]: item["length"] for item in chromosomes}
    targets = set()

    def check_window(chromosome, first, last):
        if first < 1 or last > lengths.get(chromosome, 0):
            region = f"{chromosome}:{first}-{last}"
            checker.fail(f"La finestra {region} del pannello non rientra nel FASTA {fasta.name}.",
                         f"Panel window {region} is outside FASTA {fasta.name}.")
        targets.add(chromosome)

    if caller in ("dnp", "both"):
        for site in read_dnp_list(inputs["dnp_panel"]):
            check_window(site.chromosome, site.pos1 - 1, site.pos2 + 1)
    if caller in ("snp", "both"):
        for chromosome, position in read_snp_positions(inputs["snp_panel"], for_bed=True):
            check_window(chromosome, position - 1, position + 1)
    for _, path in inputs["samples"]:
        checker.check_bam_reference(path, fasta, fai, lengths, exact_names=True, targets=targets)


def prepare_analysis(draft: dict, layout: ProjectLayout,
                     preferences: Preferences | None = None, *, language: str = "it",
                     reference_catalog=None) -> PreparedAnalysis:
    draft = deepcopy(_object(draft, "Esperimento", _DRAFT_FIELDS))
    preferences = preferences or Preferences()
    name = _text(draft.get("name"), "Nome dell’esperimento", maximum=160)
    caller = draft.get("caller")
    if caller not in {"dnp", "snp", "both", "tables"}:
        raise ValidationError("Scegliere DNP, SNP, entrambi oppure tabelle esistenti.")
    inputs: dict[str, Any] = {value: [] for value in _KINDS.values()}
    for row in _rows(draft.get("samples", []), "Campioni"):
        row = _object(row, "Campione", {"id", "path", "kind"})
        kind = row.get("kind")
        if kind not in _KINDS:
            raise ValidationError("Scegliere un formato valido per ogni campione.")
        path = _path(row.get("path"), "File del campione")
        if path is None:
            raise ValidationError("Associare un file a ogni campione.")
        inputs[_KINDS[kind]].append((_text(row.get("id"), "Nome campione", maximum=48), path))
    branches = _object(draft.get("branches", {}), "Analisi", {"DNP", "SNP"})
    for marker in ("DNP", "SNP"):
        inputs[marker.lower() + "_analyses"] = _rows(branches.get(marker, []), "Analisi", 3)
    inputs["reference"] = _path(draft.get("reference"), "Riferimento FASTA")
    # A reopened draft can carry a historical label. Only the selected local
    # entry can establish the identity of the FASTA for this new experiment.
    draft.pop("reference_genome", None)
    reference_id = draft.pop("reference_id", None)
    if reference_id is not None:
        if not inputs["samples"] or reference_catalog is None:
            raise ValidationError("Select a local reference for the BAM samples." if language == "en"
                                  else "Seleziona un riferimento locale per i campioni BAM.")
        entry = reference_catalog.resolve(_text(reference_id, "ID FASTA", maximum=128))
        if Path(entry["fasta"]) != inputs["reference"]:
            raise ValidationError("The selected FASTA differs from the catalog entry. Select the reference again."
                                  if language == "en" else
                                  "Il FASTA selezionato è diverso da quello in catalogo. Seleziona di nuovo il riferimento.")
        draft["reference_id"] = entry["id"]
        draft["reference_genome"] = {key: entry[key] for key in
                                     ("id", "build", "label", "fasta", "index", "naming", "index_sha256")}
    resources = _object(draft.get("resources", {}), "Pannelli e frequenze", {"DNP", "SNP"})
    for marker in ("DNP", "SNP"):
        fields = _object(resources.get(marker, {}), "Risorse " + marker, _RESOURCE_FIELDS)
        for key in _RESOURCE_FIELDS - {"cpi_cutoffs"}:
            inputs[marker.lower() + "_" + key] = _path(fields.get(key), marker + " " + key)
        cutoffs = []
        for row in _rows(fields.get("cpi_cutoffs", []), "Pannelli CPI", 1000):
            row = _object(row, "Pannello CPI", {"label", "path"})
            path = _path(row.get("path"), "Pannello CPI")
            if path is None:
                raise ValidationError("Selezionare il file di ogni pannello CPI.")
            cutoffs.append((_text(row.get("label"), "Nome del pannello CPI", maximum=100), path))
        inputs[marker.lower() + "_cpi_cutoffs"] = cutoffs or None
    families = _object(draft.get("families", {}), "Famiglie", {"cpi", "cpin"})
    for module, key, roles in (("cpi", "pairs", ("mother", "father")),
                               ("cpin", "trios", ("mother", "father", "child"))):
        rows = []
        for row in _rows(families.get(module, []), "Famiglie"):
            row = _object(row, "Famiglia", {"id", *roles})
            rows.append(tuple(_text(row.get(k), "Famiglia: " + k, maximum=48)
                              for k in ("id", *roles)))
        inputs[key] = rows
    settings = deepcopy(preferences.scientific_settings)
    for module, values in normalize_config(draft.get("scientific_settings", {})).items():
        settings.setdefault(module, {}).update(values)
    settings = normalize_config(settings)
    execution_values = {**preferences.execution,
                        **_object(draft.get("execution", {}), "Risorse dell’analisi",
                                  set(ExecutionOptions.__dataclass_fields__))}
    execution = ExecutionOptions(**execution_values)
    plan, _mounts, files, mapping, analyses = build_analysis_plan(
        layout=layout, caller=caller, analyses=[], **inputs)
    reference = draft.get("reference_genome")
    if reference and reference["build"] in ("grch37", "grch38"):
        _check_named_reference(reference, inputs, caller, language)
    for step in plan["steps"]:
        step.setdefault("parameters", {})["scientific_settings"] = deepcopy(
            settings.get(step["workflow"], {}))
    plan = validate_plan(plan)["plan"]
    # Store the actual reviewed values, never preferences that can later change.
    normalized_draft = {**draft, "name": name, "scientific_settings": effective_config(settings),
                        "execution": execution.as_dict()}
    evidence = tuple((path, input_stat_snapshot(path.stat())) for path in files)
    preview = {"name": name, "caller": caller, "steps": deepcopy(plan["steps"]),
               "samples": mapping, "analyses_by_marker": analyses,
               "effective_settings": effective_config(settings), "execution": execution.as_dict(),
               "input_count": len(files), "results_dir": str(layout.runs_dir)}
    if "reference_genome" in draft:
        preview["reference_genome"] = deepcopy(draft["reference_genome"])
    return PreparedAnalysis(normalized_draft, inputs, layout, settings, execution, preview, evidence, language)
