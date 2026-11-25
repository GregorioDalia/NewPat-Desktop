"""Read experiment records and scientific results for the desktop interface.

Scientific cells remain strings exactly as written by the engine.  Display metadata
adds units and labels; it never fills missing cells, recalculates genotypes, or
turns a successful process into a clinical conclusion. File capabilities are
restricted to regular, non-linked files within the selected experiment.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import stat
import tempfile
import threading
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterator

from nipat.execution.tracking import (
    WORKFLOW_STEPS, read_run_metadata, read_run_status, read_workflow_state, workflow_steps,
)
from nipat.preferences import settings_file_lock
from nipat.run_report import original_basename, sample_rows

MODULE_LABELS = {
    "dnp-call": ("Genotipi DNP", "DNP genotypes"),
    "snp-call": ("Genotipi SNP", "SNP genotypes"),
    "contamination": ("Contaminazione", "Contamination"),
    "cpi": ("CPI prenatale", "Prenatal CPI"),
    "cpin": ("CPI postnatale", "Postnatal CPI"),
}
FIELDS = {
    "site_count": ("Siti in tabella", "Sites in table"), "assigned": ("Genotipi assegnati", "Assigned genotypes"),
    "unassigned": ("Genotipi non assegnati", "Unassigned genotypes"),
    "hom_ref": ("Omozigoti REF (0/0)", "Homozygous REF (0/0)"),
    "heterozygous": ("Eterozigoti (0/1)", "Heterozygous (0/1)"),
    "hom_alt": ("Omozigoti ALT (1/1)", "Homozygous ALT (1/1)"),
    "read_observations": ("Osservazioni nei siti", "Read observations across sites"),
    "chr": ("Cromosoma", "Chromosome"), "pos": ("Posizione", "Position"),
    "pos1": ("Prima posizione", "First position"), "pos2": ("Seconda posizione", "Second position"),
    "REF": ("Allele di riferimento", "Reference allele"), "ALT": ("Allele alternativo", "Alternative allele"),
    "N_REF": ("Letture REF", "REF reads"), "N_ALT": ("Letture ALT", "ALT reads"),
    "N_Other": ("Altre letture", "Other reads"), "total_count": ("Letture totali", "Total reads"),
    "GT": ("Genotipo", "Genotype"), "GL0": ("Log-verosimiglianza · 0/0", "Log-likelihood · 0/0"),
    "GL1": ("Log-verosimiglianza · 0/1", "Log-likelihood · 0/1"),
    "GL2": ("Log-verosimiglianza · 1/1", "Log-likelihood · 1/1"),
    "combined_bases": ("Basi osservate", "Observed bases"),
    "combined_counts": ("Conteggi delle basi osservate", "Observed base counts"),
    "ratio": ("Proporzione REF tra REF e ALT", "REF proportion among REF and ALT"),
    "ratio_REF_ALT": ("Proporzione REF tra REF e ALT", "REF proportion among REF and ALT"),
    "ratio_Other": ("Proporzione delle altre letture", "Other-read proportion"),
    "Other_ratio": ("Proporzione delle altre letture", "Other-read proportion"),
    "reads_discarded_for_indels": ("Osservazioni con indel nella base centrale", "Observations with central-base indels"),
    "ratio_reads_discarded_for_indels": ("Proporzione con indel nella base centrale", "Central-base indel proportion"),
    "individuo": ("Campione", "Sample"), "sample": ("Campione", "Sample"), "Sample": ("Campione", "Sample"),
    "informative_sites": ("Siti informativi", "Informative sites"),
    "mean_contamination": ("Contaminazione media", "Mean contamination"),
    "sd_contamination": ("Deviazione standard", "Standard deviation"),
    "contamination": ("Contaminazione del sito", "Site contamination"),
    "N_unexpected": ("Letture inattese", "Unexpected reads"),
    "Pair": ("Coppia", "Pair"), "Trio": ("Trio", "Trio"), "Marker_type": ("Marcatori", "Markers"),
    "Analysis": ("Selezione dei siti", "Site selection"),
    "N_sites_mother": ("Siti informativi materni", "Maternal informative sites"),
    "N_sites_father": ("Siti paterni candidati", "Paternal candidate sites"),
    "paternal_used_at_median": ("Siti paterni usati per il CPI alla soglia mediana", "Paternal sites used for CPI at the median threshold"),
    "InfSites_mother": ("Siti informativi materni", "Maternal informative sites"),
    "InfSites_father": ("Siti paterni usati per il CPI a questa soglia", "Paternal sites used for CPI at this threshold"),
    "Median_fetal_fraction_raw": ("Frazione fetale mediana", "Median fetal fraction"),
    "Median_fetal_fraction_percent": ("Frazione fetale mediana", "Median fetal fraction"),
    "Max_logCPI": ("Massimo log₁₀(CPI)", "Maximum log₁₀(CPI)"),
    "Min_logCPI": ("Minimo log₁₀(CPI)", "Minimum log₁₀(CPI)"),
    "Median_logCPI": ("Mediana log₁₀(CPI)", "Median log₁₀(CPI)"),
    "Mean_logCPI": ("Media log₁₀(CPI)", "Mean log₁₀(CPI)"),
    "CPI_medianFF": ("log₁₀(CPI) alla soglia mediana di letture fetali", "log₁₀(CPI) at the median fetal read threshold"),
    "Error_constant": ("Probabilità di errore utilizzata", "Error probability used"),
    "Min_fetal_reads": ("Letture fetali minime", "Minimum fetal reads"),
    "Min_fetal_percent": ("Percentuale minima di letture fetali", "Minimum fetal read percentage"),
    "Min_coverage": ("Copertura minima per individuo", "Minimum coverage per trio member"),
    "Mismatch_probability": ("Peso del mismatch paterno", "Paternal mismatch weight"),
    "No_obligatory_allele_sites": ("Siti senza allele paterno obbligato", "Sites without an obligatory paternal allele"),
    "Maternal_incompatible_sites": ("Siti incompatibili tra madre e figlio", "Mother–child incompatible sites"),
    "Genotype_combination": ("Genotipi di madre e figlio", "Mother and child genotypes"),
    "Combination_selected": ("Combinazione selezionata", "Selected genotype combination"),
    "Paternity_status": ("Contributo del sito al CPI", "Site contribution to the CPI"),
    "Min_child_reads": ("Letture minime del figlio", "Minimum child reads"),
    "Through_min_child_reads": ("Fino a · letture minime del figlio", "Through · minimum child reads"),
    "N_sites": ("Siti inclusi", "Included sites"),
    "N_heterozygous_child_sites": ("Siti con figlio eterozigote", "Heterozygous child sites"),
    "N_homozygous_child": ("Siti con figlio omozigote", "Homozygous child sites"),
    "Matching_sites": ("Siti compatibili con il padre", "Sites matching the father"),
    "Mismatching_sites": ("Siti incompatibili con il padre", "Sites mismatching the father"),
    "Log10_CPI": ("log₁₀(CPI)", "log₁₀(CPI)"), "log_CPI": ("log₁₀(CPI)", "log₁₀(CPI)"),
    "CPI": ("Indice di paternità combinato (CPI)", "Combined Paternity Index (CPI)"),
    "Iteration": ("Letture fetali minime", "Minimum fetal reads"),
    "Mismatch": ("Incompatibilità paterna", "Paternal mismatch"),
    "NotMismatch": ("Siti senza incompatibilità paterna", "Sites without paternal mismatch"),
    "Cutoff": ("Pannello di selezione", "Selection panel"),
    "Quality_pass": ("Filtro di qualità superato", "Quality filter passed"),
    "Present": ("Sito presente", "Site present"),
    "Missing_total_at_zero_coverage": ("Conteggio totale mancante a copertura zero", "Missing total at zero coverage"),
    "Ref_f.pop": ("Frequenza REF nella popolazione", "Population REF frequency"),
    "Alt_f.pop": ("Frequenza ALT nella popolazione", "Population ALT frequency"),
    "Mother_homozygous": ("Madre omozigote", "Homozygous mother"),
    "Mother_child_incompatible": ("Incompatibilità madre–figlio", "Mother–child incompatibility"),
    "Required_paternal_allele": ("Allele paterno obbligato", "Obligatory paternal allele"),
    "Child_support": ("Letture a supporto dell’allele paterno", "Reads supporting the paternal allele"),
    "Child_called_alleles_supported": ("Supporto sufficiente degli alleli del figlio", "Sufficient support for child alleles"),
    "Status": ("Ammissibilità del sito", "Site eligibility"),
    "Paternity_Index": ("Indice di paternità del sito", "Site Paternity Index"),
    "Paternal_transmission": ("Probabilità di trasmissione paterna", "Paternal transmission probability"),
    "seconds": ("Tempo di elaborazione", "Processing time"),
    "resident_MB_start": ("Memoria residente iniziale", "Initial resident memory"),
    "resident_MB_end": ("Memoria residente finale", "Final resident memory"),
}
SITE_REASONS = {
    "eligible": ("Ammissibile", "Eligible"),
    "missing_call": ("Sito assente in almeno un campione", "Site missing from at least one sample"),
    "missing_population_frequency": ("Frequenza di popolazione assente", "Missing population frequency"),
    "combination_not_selected": ("Combinazione madre–figlio esclusa", "Mother–child combination excluded"),
    "child_unassigned": ("Genotipo del figlio non assegnato", "Child genotype unassigned"),
    "mother_unassigned": ("Genotipo materno non assegnato", "Mother genotype unassigned"),
    "mother_child_incompatible": ("Incompatibilità madre–figlio", "Mother–child incompatibility"),
    "mother_not_homozygous": ("Madre non omozigote", "Mother not homozygous"),
    "insufficient_child_support": ("Letture del figlio insufficienti", "Insufficient child reads"),
    "quality_filter": ("Filtro di qualità non superato", "Quality filter not passed"),
    "father_unassigned": ("Genotipo paterno non assegnato", "Father genotype unassigned"),
}
GENOTYPE_COMBINATIONS = {
    "hom_hom": ("Madre omozigote, figlio omozigote", "Homozygous mother, homozygous child"),
    "hom_het": ("Madre omozigote, figlio eterozigote", "Homozygous mother, heterozygous child"),
    "het_hom": ("Madre eterozigote, figlio omozigote", "Heterozygous mother, homozygous child"),
    "het_het": ("Madre eterozigote, figlio eterozigote", "Heterozygous mother, heterozygous child"),
}
for combination, (italian, english) in GENOTYPE_COMBINATIONS.items():
    FIELDS["N_" + combination] = ("Siti · " + italian, "Sites · " + english)
    FIELDS["Include_" + combination] = ("Includi · " + italian, "Include · " + english)

MISSING = frozenset(("", "NA", "NaN", "nan", "null"))
_MAX_PAGE = 1000
_CPI_CURVE_NAME = re.compile(r"(?:_curve|_panel_[1-9][0-9]*)\.tsv\Z")
_MAX_SUMMARY = 10000
_MAX_JSON = 32 * 1024 * 1024
_MAX_LINE = 8 * 1024 * 1024
_MAX_CURVE_ROWS = 20000
_MAX_CURVE_BYTES = 16 * 1024 * 1024


def _translation(pair, language="it"):
    return pair[1 if language == "en" else 0]


def column_description(key: str, *, language="it", samples: dict | None = None) -> dict:
    """Describe a native column without changing its identifier or values."""
    label = FIELDS.get(key)
    role = re.fullmatch(r"(.+)_(mother|father|child)", key)
    if label is None and role:
        base = column_description(role[1], language=language)["label"]
        role_label = _translation({"mother": ("madre", "mother"), "father": ("padre", "father"),
                                   "child": ("figlio", "child")}[role[2]], language)
        label = (f"{base} · {role_label}",) * 2
    if label is None and key.startswith("GT_"):
        identity = key[3:]
        display = (samples or {}).get(identity, identity)
        label = (f"Genotipo · {display}", f"Genotype · {display}")
    if label is None:
        # Future/extra scientific columns remain accessible; their source name is
        # intentional here, unlike implementation-variable names in input forms.
        label = (key, key)
    result = {"key": key, "label": _translation(label, language), "unit": None, "scale": 1}
    if key in {"mean_contamination", "contamination", "sd_contamination"}:
        result.update(unit="punti %" if key == "sd_contamination" and language != "en" else
                      "percentage points" if key == "sd_contamination" else "%", scale=100,
                      source_unit="proportion")
    elif key in {"Median_fetal_fraction_percent", "Min_fetal_percent"}:
        result["unit"] = "%"
    elif key == "Median_fetal_fraction_raw" or key.startswith("ratio") or key in {
        "Ref_f.pop", "Alt_f.pop", "Error_constant", "Mismatch_probability", "Paternal_transmission",
    }:
        result["unit"] = "proportion"
    elif key in {"GL0", "GL1", "GL2"}:
        result.update(unit="ln", description=_translation((
            "Somma di logaritmi naturali, non una probabilità normalizzata.",
            "Sum of natural logarithms, not a normalized probability."), language))
    elif key in {"CPI_medianFF", "Log10_CPI", "log_CPI", "Max_logCPI", "Min_logCPI", "Median_logCPI", "Mean_logCPI"}:
        result["unit"] = "log10"
        if key == "CPI_medianFF":
            result["description"] = _translation((
                "Valore all’iterazione più vicina al numero mediano arrotondato di letture fetali nei siti materni informativi. Lo script lo riporta a tre decimali.",
                "Value at the iteration nearest the rounded median fetal read count across informative maternal sites. The script reports it to three decimal places."), language)
    elif key == "seconds":
        result["unit"] = "s"
    elif key in {"resident_MB_start", "resident_MB_end"}:
        result.update(unit="MiB", description=_translation((
            "Misura istantanea della memoria residente; non è il picco di memoria.",
            "Resident memory at this instant; this is not peak memory."), language))
    if key == "Status":
        result["values"] = {k: _translation(v, language) for k, v in SITE_REASONS.items()}
    if key == "Genotype_combination":
        result["values"] = {k: _translation(v, language) for k, v in GENOTYPE_COMBINATIONS.items()}
    if key == "Paternity_status":
        result["values"] = {k: _translation(v, language) for k, v in {
            "match": ("Compatibile", "Match"), "mismatch": ("Incompatibile", "Mismatch"),
            "no_obligatory_allele": ("Nessun allele paterno obbligato", "No obligatory paternal allele"),
        }.items()}
    if key == "Analysis":
        result["values"] = {
            "all_compatible_sites": _translation(("Tutti i siti compatibili con la madre", "All sites compatible with the mother"), language),
            "heterozygous_child_sites": _translation(("Siti con figlio eterozigote", "Heterozygous child sites"), language),
        }
    if "indels" in key:
        result["description"] = _translation((
            "Osservazioni nella base centrale, prima del filtro sull’intera finestra.",
            "Central-base observations before filtering the whole window."), language)
    return result


def _cpi_guides(run, descriptor, workflow):
    """Read the two guides emitted by R for this step, including older models."""
    try:
        path = _scoped(run, descriptor["relative_path"], file=True)
        settings = _json(path, max_bytes=4 * 1024 * 1024, parse_float=Decimal,
                         expected_sha256=descriptor.get("recorded_sha256"))
        if (type(settings.get("schema_version")) is not int or settings["schema_version"] != 1
                or settings.get("workflow") != workflow):
            return None
        parameters = settings["parameters"]
        values = [parameters[name] for name in ("log_cpi_lower", "log_cpi_upper")]
        if any(type(v) not in (int, Decimal) for v in values):
            return None
        lower, upper = map(Decimal, values)
        if lower.is_finite() and upper.is_finite() and lower < upper:
            return lower, upper
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation):
        pass
    return None


def _reported_cpi_band(row, guides, marker, workflow):
    """Compare the published, rounded estimate, never an inferred unrounded CPI."""
    if guides is None or row.get("Marker_type", marker) != marker:
        return None
    support = ("N_sites_mother", "N_sites_father") if workflow == "cpi" else ("N_sites",)
    if not all(_read_count(row.get(key)) for key in support):
        return None
    try:
        estimate = Decimal(row["CPI_medianFF" if workflow == "cpi" else "Log10_CPI"])
    except (KeyError, TypeError, InvalidOperation):
        return None
    if not estimate.is_finite():
        return None
    lower, upper = guides
    if estimate < lower:
        position = "below"
    elif estimate == lower:
        position = "at_lower"
    elif estimate < upper:
        position = "between"
    elif estimate == upper:
        position = "at_upper"
    else:
        position = "above"
    return {"position": position, "lower": str(lower), "upper": str(upper)}


def _read_count(value):
    if value is None or value in MISSING:
        return None
    try:
        number = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        return None
    # Native counts are integers. Keep their sum exact, including R's scientific
    # notation, and reject implausibly large exponents before allocating an int.
    if not number.is_finite() or number < 0 or number.adjusted() > 308 or number != number.to_integral_value():
        return None
    return int(number)


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _scoped(root: Path, relative: str, *, file=False) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or "\x00" in relative:
        raise ValueError("Identificativo del risultato non valido.")
    parts = PurePosixPath(relative)
    if parts.is_absolute() or PureWindowsPath(relative).is_absolute() or ".." in parts.parts:
        raise ValueError("Il percorso del risultato deve appartenere all’esperimento.")
    current = root
    for component in parts.parts:
        current /= component
        if _is_link(current):
            raise ValueError("I collegamenti esterni non sono consultabili come risultati.")
    if not current.resolve().is_relative_to(root):
        raise ValueError("Risultato esterno alla cartella dell’esperimento.")
    if file and (not current.exists() or not stat.S_ISREG(current.stat().st_mode)):
        raise ValueError("Il file del risultato non è disponibile.")
    return current


def _json(path: Path, max_bytes=_MAX_JSON, *, parse_float=float, expected_sha256=None) -> dict:
    if path.stat().st_size > max_bytes:
        raise ValueError("Il documento dei risultati supera il limite di lettura.")
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Il documento dei risultati supera il limite di lettura.")
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Il documento dei risultati è cambiato dopo la verifica dell’esperimento.")
    try:
        value = json.loads(raw.decode("utf-8-sig"), parse_float=parse_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Il documento dei risultati non è leggibile.") from exc
    if not isinstance(value, dict):
        raise ValueError("Il documento dei risultati deve contenere un oggetto.")
    return value


def _lines(stream):
    while line := stream.readline(_MAX_LINE + 1):
        if len(line) > _MAX_LINE:
            raise ValueError("Una riga del risultato supera il limite di lettura.")
        yield line


def _rows(path: Path) -> Iterator[dict]:
    """Stream native cells with bounded individual rows and exact decimal strings."""
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(_lines(stream), delimiter="," if path.suffix.lower() == ".csv" else "\t", strict=True)
            columns = reader.fieldnames or []
            if not columns or len(columns) != len(set(columns)) or any(not c for c in columns):
                raise ValueError("La tabella ha colonne mancanti o duplicate.")
            for number, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise ValueError(f"La riga {number} della tabella non è completa.")
                yield row
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("Il formato della tabella non è leggibile.") from exc


def _columns(path: Path) -> list[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        try:
            row = next(csv.reader(_lines(stream), delimiter="," if path.suffix.lower() == ".csv" else "\t", strict=True), [])
        except (csv.Error, UnicodeError) as exc:
            raise ValueError("Le colonne della tabella non sono leggibili.") from exc
    if not row or len(row) != len(set(row)) or any(not c for c in row):
        raise ValueError("La tabella ha colonne mancanti o duplicate.")
    return row


def _signature(path):
    value = path.stat()
    return value.st_size, value.st_mtime_ns, value.st_ino


def _file_kind(path):
    return {".pdf": "pdf", ".csv": "table", ".tsv": "table", ".txt": "table",
            ".json": "json", ".log": "text", ".html": "html"}.get(path.suffix.lower(), "binary")


def _file_label_it(name):
    if name.startswith("full_output_") or name == "SNPcall_output.txt":
        return "Conteggi e genotipi"
    if name in {"output_AllGenotypes.txt", "SNPcall_AllGenotypes.txt", "merged_genotypes.tsv"}:
        return "Matrice dei genotipi"
    fixed = {"contamination_summary.txt": "Riepilogo della contaminazione", "Summary_FetalFraction_CPI.csv": "Frazione fetale e CPI",
             "Summary_Postnatal_CPI.txt": "Riepilogo CPI postnatale", "scientific-settings.json": "Impostazioni scientifiche",
             "resources.tsv": "Tempo e memoria", "Unassigned_genotypes.pdf": "Genotipi non assegnati",
             "All_CPIplots.pdf": "Tutti i grafici di paternità", "run.json": "Provenienza dell’esperimento",
             "execution.log": "Registro dell’esecuzione", "gui.json": "Configurazione dell’interfaccia",
             "sample-map.tsv": "Corrispondenza dei campioni", "run-report.html": "Rapporto dell’esperimento",
             "scientific-validation.json": "Controlli dei risultati scientifici"}
    if name in fixed:
        return fixed[name]
    for fragment, label in (("N_genotypes", "Distribuzione dei genotipi"), ("Alt_read_count", "Distribuzione delle letture ALT"),
                            ("Ref_read_count", "Distribuzione delle letture REF"), ("Other_read_count", "Distribuzione delle altre letture"),
                            ("UpSet", "Loci con genotipo assegnato in comune fra campioni")):
        if fragment in name:
            return label
    if name.startswith("contamination_"):
        return "Contaminazione per sito"
    if name.endswith(("_sites.tsv", "_sites.txt")):
        return "Siti inclusi ed esclusi"
    if _CPI_CURVE_NAME.search(name):
        return "Valori della curva"
    if name.endswith("_CPIplot.pdf"):
        return "Grafico di paternità"
    return name


def _file_label(name, language="it"):
    label = _file_label_it(name)
    english = {
        "Conteggi e genotipi": "Counts and genotypes", "Matrice dei genotipi": "Genotype matrix",
        "Riepilogo della contaminazione": "Contamination summary", "Frazione fetale e CPI": "Fetal fraction and CPI",
        "Riepilogo CPI postnatale": "Postnatal CPI summary", "Impostazioni scientifiche": "Scientific settings",
        "Tempo e memoria": "Time and memory", "Genotipi non assegnati": "Unassigned genotypes",
        "Tutti i grafici di paternità": "All paternity plots", "Provenienza dell’esperimento": "Experiment provenance",
        "Registro dell’esecuzione": "Execution log", "Configurazione dell’interfaccia": "Interface configuration",
        "Corrispondenza dei campioni": "Sample mapping", "Rapporto dell’esperimento": "Experiment report",
        "Controlli dei risultati scientifici": "Scientific result checks",
        "Distribuzione dei genotipi": "Genotype distribution", "Distribuzione delle letture ALT": "ALT read distribution",
        "Distribuzione delle letture REF": "REF read distribution", "Distribuzione delle altre letture": "Other-read distribution",
        "Loci con genotipo assegnato in comune fra campioni": "Shared loci with assigned genotypes", "Contaminazione per sito": "Per-site contamination",
        "Siti inclusi ed esclusi": "Included and excluded sites", "Valori della curva": "Curve values",
        "Grafico di paternità": "Paternity plot",
    }
    return english.get(label, label) if language == "en" else label


@dataclass
class _ArchiveEntry:
    # Keep searchable metadata, never the workflow state, validation reports or BAM inputs.
    stamp: tuple
    started: str
    searchable: str
    is_workflow: bool
    recorded_active: bool
    filters: tuple | None = None
    workflow_stamp: tuple | None = None


def _file_stamp(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    return info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_ino


def _run_name(gui, metadata, run_id):
    name = gui.get("name") or metadata.get("run_name") or run_id
    return name if isinstance(name, str) else run_id


def _gui_metadata(run):
    try:
        path = _scoped(run, "gui.json")
        if path.is_file():
            snapshot = _json(path, max_bytes=4 * 1024 * 1024)
            if snapshot.get("schema_version") == 1:
                return snapshot
    except (OSError, ValueError):
        pass
    return {}


def _observed_steps(run, metadata):
    workflow = metadata.get("workflow")
    declared = workflow_steps(metadata, include_markers=True)
    state = read_workflow_state(run, workflow, metadata)
    observed = {step["id"]: step for step in state["steps"]}
    steps = []
    for step in declared:
        marker = step.get("marker")
        if step["workflow"] in {"dnp-call", "snp-call"}:
            marker = "DNP" if step["workflow"] == "dnp-call" else "SNP"
        if marker not in {"DNP", "SNP"}:
            marker = "DNP"  # Legacy preset workflows only consume DNP tables.
        steps.append({"id": step["id"], "module": step["workflow"], "marker": marker,
                      "status": observed[step["id"]].get("status"), "sample_id": step.get("sample"),
                      "output_prefix": f"output/workflow/steps/{step['id']}/output/"})
    return steps, state


def _standalone_marker(metadata):
    parameters = metadata.get("parameters")
    default = "SNP" if metadata.get("workflow") == "snp-call" else "DNP"
    return parameters.get("marker_type", default) if isinstance(parameters, dict) else default


class ResultsStore:
    """Scope every read to a configured local archive, never a frontend path."""

    def __init__(self, results_root: Path | str, *, language="it", registry_path: Path | str | None = None,
                 status_observer=None):
        self.root = Path(results_root).expanduser().resolve()
        self.language = "en" if language == "en" else "it"
        self.registry_path = Path(registry_path).expanduser().absolute() if registry_path else self.root / "gui-imports.json"
        self._stats_cache: dict[tuple, dict] = {}
        self._archive_cache: dict[str, _ArchiveEntry] = {}
        self._archive_lock = threading.Lock()
        self.status_observer = status_observer
        self._lock = threading.RLock()

    def _run(self, run_id: str, imports=None) -> Path:
        if isinstance(run_id, str) and run_id.startswith("imported-"):
            records = self._imports() if imports is None else imports
            if run_id not in records:
                raise ValueError("Esperimento importato non registrato.")
            path = Path(records[run_id])
            if _is_link(path) or not path.is_absolute() or path.resolve() != path:
                raise ValueError("Cartella importata non valida.")
            path = path.resolve()
        else:
            path = _scoped(self.root, run_id)
        if not path.is_dir():
            raise ValueError("L’esperimento non è disponibile nell’archivio selezionato.")
        _scoped(path, "run.json", file=True)
        return path

    def _registry(self) -> dict:
        if not self.registry_path.is_file():
            return {"schema_version": 1, "imports": {}, "hidden": []}
        if _is_link(self.registry_path):
            raise ValueError("Il registro degli esperimenti non può essere un collegamento.")
        value = _json(self.registry_path, max_bytes=4 * 1024 * 1024)
        entries = value.get("imports")
        if value.get("schema_version") != 1 or not isinstance(entries, dict) or any(
            not isinstance(k, str) or not re.fullmatch(r"imported-[a-f0-9]{32}", k) or not isinstance(v, str)
            for k, v in entries.items()
        ):
            raise ValueError("Registro degli esperimenti importati non valido.")
        hidden = value.get("hidden", [])
        if not isinstance(hidden, list) or any(not isinstance(p, str) or not Path(p).is_absolute() for p in hidden):
            raise ValueError("Registro degli esperimenti nascosti non valido.")
        return {"schema_version": 1, "imports": entries, "hidden": hidden}

    def _imports(self) -> dict[str, str]:
        return self._registry()["imports"]

    def _write_registry(self, value):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_link(self.registry_path):
            raise ValueError("Il registro degli esperimenti non può essere un collegamento.")
        fd, temporary = tempfile.mkstemp(prefix=".gui-imports-", suffix=".json", dir=self.registry_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            os.replace(temporary, self.registry_path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def remove_run(self, run_id):
        """Hide only the archive entry. The service checks activity first."""
        self.hide_path(self._run(run_id))
        return {"removed": True, "run_id": run_id, "outputs_preserved": True}

    def hide_path(self, path: Path):
        """Record a verified archive or session job path without changing its files."""
        with settings_file_lock(self.registry_path):
            value = self._registry()
            value["hidden"] = sorted(set(value["hidden"]) | {str(path)})
            self._write_registry(value)

    def forget_missing_import(self, run_id):
        """Allow dismissal of a registered location after its data was moved."""
        if not isinstance(run_id, str) or not run_id.startswith("imported-"):
            return False
        with settings_file_lock(self.registry_path):
            registry = self._registry()
            registered = registry["imports"].get(run_id)
            if registered is None or (Path(registered) / "run.json").is_file():
                return False
            del registry["imports"][run_id]
            self._write_registry(registry)
            return True

    def identifier_for_path(self, path: Path) -> str:
        if path.is_relative_to(self.root):
            return path.relative_to(self.root).as_posix()
        return "imported-" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]

    def session_run_id(self, path: Path) -> str:
        """Resolve the exact directory recorded by a desktop job, even after an archive change."""
        if not path.is_absolute() or _is_link(path) or path.resolve() != path:
            raise ValueError("Cartella dell’esperimento non valida.")
        identifier = self.identifier_for_path(path)
        if path.is_relative_to(self.root):
            self._run(identifier)
        else:
            _scoped(path, "run.json", file=True)
            read_run_metadata(path)
            with settings_file_lock(self.registry_path):
                registry = self._registry()
                if registry["imports"].get(identifier) != str(path):
                    registry["imports"][identifier] = str(path)
                    self._write_registry(registry)
        return identifier

    def register_run(self, path: Path | str) -> dict:
        """Register a user-selected run/archive in place; copy no input/output data.

        The host must call this only for an explicitly selected native directory.
        Registration grants read access solely to run-owned files discovered here.
        """
        selected = Path(path).expanduser()
        if _is_link(selected) or not selected.is_dir():
            raise ValueError("Seleziona una cartella di esperimenti esistente, non un collegamento.")
        selected = selected.resolve()
        imported = {}
        for directory, directories, files in os.walk(selected, followlinks=False):
            current = Path(directory)
            directories[:] = [name for name in sorted(directories) if not _is_link(current / name)
                              and name not in {"output", "work", "inputs", ".git"}]
            if "run.json" not in files:
                continue
            directories[:] = []
            _scoped(current, "run.json", file=True)
            read_run_metadata(current)
            imported[self.identifier_for_path(current)] = str(current)
        if not imported:
            raise ValueError("La cartella non contiene esperimenti NewPat con run.json.")
        # Other application windows may import or dismiss cards sharing this
        # registry. Hold the sidecar lock only for the read/merge/write.
        with settings_file_lock(self.registry_path):
            registry = self._registry()
            registry["imports"].update({key: value for key, value in imported.items()
                                        if not Path(value).is_relative_to(self.root)})
            registry["hidden"] = sorted(set(registry["hidden"]) - set(imported.values()))
            self._write_registry(registry)
        return {"imported": list(imported), "count": len(imported)}

    @staticmethod
    def _page(offset, limit):
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("Posizione della pagina non valida.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_PAGE:
            raise ValueError("La pagina deve contenere da 1 a 1000 righe.")
        return offset, limit

    def _metadata(self, run_id):
        run = self._run(run_id)
        return run, read_run_metadata(run)

    def _archive_locations(self, registry):
        hidden = set(registry["hidden"])
        imports = {Path(path): identifier for identifier, path in registry["imports"].items()}
        for directory, directories, files in os.walk(self.root, followlinks=False):
            path = Path(directory)
            if "run.json" in files:
                directories[:] = []
                imports.pop(path, None)  # An imported directory may now belong to this archive.
                if str(path) not in hidden and not _is_link(path / "run.json"):
                    yield path.relative_to(self.root).as_posix(), path, False
            else:
                directories[:] = [name for name in directories
                                  if name not in {"output", "inputs", "work", ".git"} and not _is_link(path / name)]
        for path, identifier in imports.items():
            if str(path) not in hidden:
                yield identifier, path, True

    def _archive_entry(self, run_id, run):
        stamp = (run, _file_stamp(run / "run.json"), _file_stamp(run / "gui.json"))
        cached = self._archive_cache.get(run_id)
        if cached and cached.stamp == stamp:
            return cached
        metadata = read_run_metadata(run)
        samples = sample_rows(metadata)
        name = _run_name(_gui_metadata(run), metadata, run_id)
        started = metadata.get("started_at")
        started = started if isinstance(started, str) else ""
        searchable = " ".join([name, run_id, started, *(s["original_name"] for s in samples),
                               *(s["sample_id"] for s in samples)]).casefold()
        workflow = metadata.get("workflow") in WORKFLOW_STEPS
        active = metadata.get("status") in ("running", "preparing")
        entry = _ArchiveEntry(stamp, started, searchable, workflow, active)
        if not workflow and not active:
            entry.filters = (read_run_status(run, metadata), (_standalone_marker(metadata),), None)
        return entry

    def _archive_filters(self, run, entry):
        # Only filtered views inspect off-page workflow state. A running record
        # must consult the observer again even if no files have changed.
        state_stamp = None
        if entry.is_workflow:
            try:
                state_stamp = _file_stamp(_scoped(run, "output/workflow/workflow-state.json"))
            except (OSError, ValueError):
                state_stamp = None
        if entry.filters is not None and entry.workflow_stamp == state_stamp and not entry.recorded_active:
            return entry.filters
        metadata = read_run_metadata(run)
        if entry.is_workflow:
            try:
                steps, _ = _observed_steps(run, metadata)
                markers = tuple({s["marker"] for s in steps})
            except (OSError, ValueError, KeyError, TypeError):
                markers = ()
        else:
            markers = (_standalone_marker(metadata),)
        observed = self.status_observer(run, metadata) if self.status_observer else None
        status = observed["status"] if observed else read_run_status(run, metadata)
        filters = (status, markers, observed if entry.recorded_active else None)
        if not entry.recorded_active:
            entry.filters, entry.workflow_stamp = filters, state_stamp
        return filters

    def _unreadable_card(self, identifier, path, imported, exc):
        name = (_translation(("Esperimento importato non disponibile", "Imported experiment unavailable"),
                             self.language) if imported else path.name)
        row = {"id": identifier, "name": name, "status": "unreadable", "workflow": None,
               "started_at": None, "finished_at": None, "version": None, "samples": [],
               "modules": [], "markers": [], "warning": str(exc)}
        if imported:
            row["can_remove"] = not (path / "run.json").is_file()
        return row

    def list_runs(self, query="", status=None, offset=0, limit=100, marker=None, run_id=None) -> dict:
        self._page(offset, limit)
        if not isinstance(query, str) or len(query) > 1000:
            raise ValueError("Ricerca dell’archivio non valida.")
        if marker not in (None, "DNP", "SNP"):
            raise ValueError("Marcatore non valido.")
        if run_id is not None and (not isinstance(run_id, str) or not run_id):
            raise ValueError("Identificativo del risultato non valido.")
        query = query.casefold()
        registry = self._registry()
        found, updated = [], {}
        archive_total, checking = 0, False
        with self._archive_lock:
            for identifier, path, imported in self._archive_locations(registry):
                archive_total += 1
                if run_id is not None and identifier != run_id:
                    if identifier in self._archive_cache:
                        updated[identifier] = self._archive_cache[identifier]
                    continue
                error_row, observation = None, None
                try:
                    run = self._run(identifier, registry["imports"])
                    entry = self._archive_entry(identifier, run)
                    updated[identifier] = entry
                    if query not in entry.searchable:
                        continue
                    if marker or status:
                        actual, markers, observation = self._archive_filters(run, entry)
                        if marker and marker not in markers:
                            continue
                        checking |= bool(status and observation and observation.get("status_reason") == "checking")
                        if status and status != actual:
                            continue
                    started = entry.started
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    error_row = self._unreadable_card(identifier, path, imported, exc)
                    if (marker or status and status != "unreadable"
                            or query not in f"{error_row['name']} {identifier}".casefold()):
                        continue
                    started = ""
                found.append((started, identifier, path, imported, error_row, observation))
            self._archive_cache = updated

        found.sort(key=lambda row: (row[0], row[1]), reverse=True)
        runs = []
        for _, identifier, path, imported, row, observation in found[offset:offset + limit]:
            if row is None:
                try:
                    context = self._context(identifier, imports=registry["imports"], observation=observation)
                    row = self._run_record(identifier, context)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    row = self._unreadable_card(identifier, path, imported, exc)
            runs.append(row)
        return {"runs": runs, "total": len(found), "archive_total": archive_total,
                "checking_status": checking, "offset": offset, "limit": limit,
                "has_more": offset + limit < len(found)}

    def _context(self, run_id, *, imports=None, observation=None) -> dict:
        run = self._run(run_id, imports)
        metadata = read_run_metadata(run)
        parameters = metadata.get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        samples = [{"id": s["sample_id"], "label": s["original_name"], "filename": original_basename(s["original_path"]),
                    "path": s["original_path"], "role": s["role"]} for s in sample_rows(metadata)]
        gui = _gui_metadata(run)
        warnings, steps, documents = [], [], []
        workflow = metadata.get("workflow")
        if workflow in WORKFLOW_STEPS:
            try:
                steps, state = _observed_steps(run, metadata)
                documents.append((state, "output/workflow/", None))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                warnings.append({"code": "archive.workflow", "message": str(exc)})
        else:
            marker = _standalone_marker(metadata)
            steps = [{"id": "standalone", "module": workflow, "marker": marker,
                      "status": read_run_status(run, metadata), "sample_id": samples[0]["id"] if len(samples) == 1 else None,
                      "output_prefix": "output/"}]
            try:
                validation = _scoped(run, "work/scientific-validation.json")
                if validation.is_file():
                    documents.append((_json(validation), "", steps[0]))
            except (OSError, ValueError) as exc:
                warnings.append({"code": "archive.validation", "message": str(exc)})
        seen_warnings = set()
        def collect_warnings(value, origin="", depth=0):
            if depth > 25:
                return
            if isinstance(value, list):
                for item in value:
                    collect_warnings(item, origin, depth + 1)
            elif isinstance(value, dict):
                origin = value.get("id", origin) if isinstance(value.get("id", origin), str) else origin
                for key, child in value.items():
                    if key in {"quality_warnings", "input_warnings"} and isinstance(child, list):
                        for warning in child:
                            if not isinstance(warning, dict):
                                continue
                            signature = json.dumps(warning, sort_keys=True, ensure_ascii=False)
                            if signature not in seen_warnings and len(seen_warnings) < 1000:
                                seen_warnings.add(signature)
                                warnings.append({**warning, "step_id": origin or None})
                    else:
                        collect_warnings(child, origin, depth + 1)
        for document, _, _ in documents:
            collect_warnings(document)
        if observation is None and self.status_observer:
            observation = self.status_observer(run, metadata)
        if observation and observation["status"] == "interrupted" and observation.get("status_reason") == "abandoned":
            # Display the interrupted lifecycle without changing completed step
            # evidence or any original workflow/run document.
            for step in steps:
                if step["status"] in {"running", "pending", "preparing"}:
                    step["status"] = "interrupted"
        return {"run": run, "metadata": metadata, "parameters": parameters, "samples": samples, "gui": gui,
                "steps": steps, "documents": documents, "warnings": warnings, "observation": observation}

    @staticmethod
    def _igv_sources(context):
        def records(rows):
            return (row for row in rows if isinstance(row, dict)) if isinstance(rows, list) else ()

        draft = context["gui"].get("draft")
        if isinstance(draft, dict):
            reference, samples = draft.get("reference"), draft.get("samples")
        else:
            parameters = context["parameters"]
            plan = parameters.get("plan")
            if not isinstance(plan, dict):
                return None, []
            mounts = {row["container_path"]: row["host_path"]
                      for row in records(context["metadata"].get("input_mounts"))
                      if isinstance(row.get("container_path"), str) and isinstance(row.get("host_path"), str)}
            references = set()
            for step in records(plan.get("steps")):
                inputs = step.get("inputs")
                if step.get("workflow") in ("dnp-call", "snp-call") and isinstance(inputs, dict):
                    path = inputs.get("reference")
                    if isinstance(path, str) and path in mounts:
                        references.add(mounts[path])
            reference = next(iter(references)) if len(references) == 1 else None
            bams = {row["id"] for row in records(plan.get("samples"))
                    if row.get("kind") == "bam" and isinstance(row.get("id"), str)}
            samples = [{"id": row.get("biological_id") or row["sample_id"],
                        "path": row.get("original_path"), "kind": "bam"}
                       for row in records(parameters.get("sample_mapping"))
                       if isinstance(row.get("sample_id"), str) and row["sample_id"] in bams]
        tracks = [{"name": row.get("id") or Path(row["path"]).name, "path": row["path"]}
                  for row in records(samples) if row.get("kind") == "bam"
                  and isinstance(row.get("path"), str) and row["path"]]
        return reference if isinstance(reference, str) else None, tracks

    def igv_sources(self, run_id):
        context = self._context(run_id)
        fasta, tracks = self._igv_sources(context)
        reference = {"fasta": fasta, "index": ""}
        draft = context["gui"].get("draft")
        recorded = draft.get("reference_genome") if isinstance(draft, dict) else None
        if (isinstance(recorded, dict) and fasta and recorded.get("fasta") == fasta
                and recorded.get("build") in ("grch37", "grch38", "custom")
                and recorded.get("index") == fasta + ".fai"):
            reference["index"] = recorded["index"]
            if recorded["build"] != "custom":
                reference["build"] = recorded["build"]
            for key in ("fasta_sha256", "index_sha256", "gzi_sha256"):
                if key in recorded:
                    reference[key] = recorded[key]
        if fasta:
            # Older runs may have captured full digests in the input manifest.
            evidence = context.get("metadata", {}).get("inputs", [])
            files = {row["path"]: row["sha256"] for row in evidence if isinstance(row, dict)
                     and isinstance(row.get("path"), str) and row.get("sha256")} if isinstance(evidence, list) else {}
            required = {"fasta_sha256": fasta, "index_sha256": fasta + ".fai"}
            if fasta.lower().endswith((".gz", ".bgz", ".bgzf")):
                required["gzi_sha256"] = fasta + ".gzi"
            for key, path in required.items():
                if key not in reference and path in files:
                    reference[key] = files[path]
            if not required.keys() <= reference.keys():
                reference["historical_identity_incomplete"] = True
        return reference, tracks

    def _run_record(self, run_id, context=None):
        ctx = context or self._context(run_id)
        md, gui = ctx["metadata"], ctx["gui"]
        name = _run_name(gui, md, run_id)
        state = dict(ctx.get("observation") or {"status": read_run_status(ctx["run"], md)})
        notes = {
            "checking": ("Verifica dello stato dell’esperimento in corso.", "Checking the experiment’s current state."),
            "abandoned": ("L’esecuzione non risulta più attiva e non è stata finalizzata. I risultati possono essere parziali; puoi rieseguire l’esperimento.", "The run is no longer active and was not finalized. Results may be partial; you can run the experiment again."),
            "unavailable": ("Impossibile confermare se l’esecuzione precedente è ancora attiva. Il runtime potrebbe non essere disponibile oppure un’altra analisi è in corso.", "The previous run’s activity could not be confirmed. The runtime may be unavailable or another analysis may be active."),
            "external": ("Questo esperimento importato non ha uno stato finale registrato. La sua attività non è verificabile su questo computer.", "This imported experiment has no recorded final status. Its activity cannot be verified on this computer."),
            "external_active": ("Il runtime segnala un’esecuzione ancora attiva, avviata fuori da questa sessione.", "The runtime reports an active run started outside this session."),
        }
        state["status_note"] = _translation(notes[state["status_reason"]], self.language) if state.get("status_reason") in notes else None
        source = md.get("source")
        version = source.get("nipat_version") if isinstance(source, dict) else None
        reference, tracks = self._igv_sources(ctx)
        has_igv_inputs = bool(reference and tracks)
        return {"id": run_id, "name": name, "workflow": md.get("workflow"), **state,
                "has_igv_inputs": has_igv_inputs, "started_at": md.get("started_at"),
                "finished_at": md.get("finished_at"), "version": version,
                "samples": ctx["samples"], "modules": sorted({s["module"] for s in ctx["steps"] if s["module"]}),
                "markers": sorted({s["marker"] for s in ctx["steps"] if s["marker"]}),
                "warnings": ctx["warnings"]}

    def _artifact_index(self, context):
        index, families = {}, []
        step_by_id = {s["id"]: s for s in context["steps"]}
        samples = {s["id"]: s for s in context["samples"]}
        parameters = context["parameters"]
        def actual_sample(sample, role=None):
            if not isinstance(sample, str):
                return None
            if sample in samples:
                return sample
            if role:
                candidate = parameters.get(role + "_prefix", role.title()) + sample
                if candidate in samples:
                    return candidate
            return sample
        def visit(value, prefix, inherited, depth=0):
            if depth > 30:
                return
            if isinstance(value, list):
                for item in value:
                    visit(item, prefix, inherited, depth + 1)
                return
            if not isinstance(value, dict):
                return
            info = dict(inherited)
            if isinstance(value.get("id"), str) and value["id"] in step_by_id and "workflow" in value:
                info.update(step_by_id[value["id"]])
                info["step_id"] = info.pop("id")
            if isinstance(value.get("sample"), str):
                info["sample_id"] = actual_sample(value["sample"])
            for key in ("native_name", "analysis", "cutoff"):
                if key in value:
                    info[key] = value[key]
            family_key = "pair" if "native_pair" in value else "trio" if "native_trio" in value else None
            if family_key:
                info.update(family_id=value.get(family_key), native_family=value.get("native_" + family_key))
                family = {"id": info["family_id"], "native_id": info["native_family"],
                          "module": info.get("module"), "marker": info.get("marker"), "step_id": info.get("step_id")}
                for role in ("mother", "father", "child"):
                    ref = value.get(role)
                    if isinstance(ref, dict):
                        family[role] = actual_sample(ref.get("sample"), role)
                if family not in families:
                    families.append(family)
            path = value.get("path")
            if isinstance(path, str):
                relative = prefix + path
                try:
                    _scoped(context["run"], relative)
                except ValueError:
                    pass
                else:
                    # Do not use presentation copies to overwrite canonical identity.
                    if "/presentation/" not in relative:
                        record = {k: v for k, v in info.items() if k in {"module", "marker", "step_id", "sample_id", "family_id", "native_family", "native_name", "analysis", "cutoff"}}
                        support = value.get("prenatal_support")
                        if isinstance(support, dict):
                            used = support.get("paternal_used_at_median")
                            if type(used) is int and used >= 0:
                                record["paternal_used_at_median"] = used
                        if isinstance(value.get("sha256"), str):
                            record["recorded_sha256"] = value["sha256"]
                        index[relative] = {**index.get(relative, {}), **record}
            for key, item in value.items():
                if key not in {"source", "request", "command", "script_sha256"}:
                    visit(item, prefix, info, depth + 1)
        for document, prefix, standalone in context["documents"]:
            inherited = {} if standalone is None else {"module": standalone["module"], "marker": standalone["marker"], "step_id": standalone["id"]}
            visit(document, prefix, inherited)
        return index, families

    def metadata(self, run_id) -> dict:
        """Validated original metadata for rebuilding a plan; never frontend paths."""
        return self._metadata(run_id)[1]

    def get_run(self, run_id) -> dict:
        context = self._context(run_id)
        record = self._run_record(run_id, context)
        _, families = self._artifact_index(context)
        settings = []
        for step in context["steps"]:
            try:
                path = _scoped(context["run"], step["output_prefix"] + "scientific-settings.json")
                if path.is_file():
                    settings.append({"step_id": step["id"], "module": step["module"], "marker": step["marker"], "document": _json(path)})
            except (OSError, ValueError) as exc:
                record["warnings"].append({"code": "archive.settings", "message": str(exc)})
        execution = context["gui"].get("execution", context["metadata"].get("execution_options"))
        if context["metadata"].get("concurrent_execution"):
            execution = context["metadata"].get("execution_options", execution)
        record.update(steps=context["steps"], families=families, settings=settings,
                      draft=context["gui"].get("draft"), execution=execution,
                      configuration_source="gui" if context["gui"].get("draft") else "run",
                      recorded_parameters=context["parameters"], error=context["metadata"].get("error"))
        return record

    def _file_descriptors(self, run_id, context=None, *, artifact_index=None):
        context = context or self._context(run_id)
        run = context["run"]
        index, families = artifact_index if artifact_index is not None else self._artifact_index(context)
        samples = {s["id"]: s for s in context["samples"]}
        paths = []
        output = _scoped(run, "output")
        if output.is_dir():
            for directory, directories, files in os.walk(output, followlinks=False):
                current = Path(directory)
                directories[:] = sorted(name for name in directories if not _is_link(current / name)
                                        and name not in {"work", "inputs", "parallel", "__pycache__"})
                for name in sorted(files):
                    path = current / name
                    if _is_link(path) or not stat.S_ISREG(path.stat().st_mode):
                        continue
                    paths.append(path)
        # Standalone runs keep artifact identities and quality warnings here;
        # retain that evidence when exported results are opened elsewhere.
        # Other work files remain private and are not included in the export.
        for name in ("run.json", "gui.json", "execution.log", "run-report.html", "sample-map.tsv",
                     "work/scientific-validation.json"):
            try:
                path = _scoped(run, name)
                if path.is_file():
                    paths.append(path)
            except ValueError:
                continue
        descriptors = []
        for path in paths:
            relative = path.relative_to(run).as_posix()
            info = dict(index.get(relative, {}))
            step = next((step for step in context["steps"] if relative.startswith(step["output_prefix"])), None)
            if step:
                for key in ("module", "marker", "sample_id"):
                    if key not in info and step.get(key) is not None:
                        info[key] = step[key]
                info.setdefault("step_id", step["id"])
            # If no validated artifact mapping exists, retain the native alias.
            # Never infer a biological role from a filename or sample ordering.
            if step and "plots" in path.parts and not info.get("sample_id"):
                native_alias = path.parent.name
                mapped = next((v for v in index.values() if v.get("step_id") == step["id"]
                               and v.get("native_name") == native_alias and v.get("sample_id")), None)
                if mapped:
                    info["sample_id"] = mapped["sample_id"]
            if relative.startswith("output/workflow/snp_summary/"):
                info.update(module="snp-call", marker="SNP", group_id=PurePosixPath(relative).parts[3])
            sample = info.get("sample_id")
            family = next((f for f in families if f["id"] == info.get("family_id") and f.get("step_id") == info.get("step_id")), None)
            display = samples.get(sample, {}).get("label", sample)
            size = path.stat().st_size
            descriptors.append({"id": hashlib.sha256(relative.encode("utf-8")).hexdigest()[:32],
                                "relative_path": relative, "name": path.name, "kind": _file_kind(path),
                                "label": _file_label(path.name, self.language), "size_bytes": size,
                                "canonical": "presentation" not in path.relative_to(run).parts,
                                "sample_label": display, "family_label": self._family_label(family, samples),
                                **info})
        descriptors.sort(key=lambda f: (not f["canonical"], f.get("module", ""), f.get("marker", ""), f["relative_path"]))
        return descriptors

    @staticmethod
    def _family_label(family, samples):
        if not family:
            return None
        ids = [family.get(role) for role in ("mother", "father", "child") if family.get(role)]
        return " / ".join(samples.get(s, {}).get("label", s) for s in ids) or family["id"]

    def files(self, run_id) -> list[dict]:
        return self._file_descriptors(run_id)

    def caller_count_tables(self, run_id, successful_steps, sample_ids):
        """Resolve reusable native counts from one inventory and check recorded hashes."""
        if not successful_steps:
            return
        context = self._context(run_id)
        artifacts = self._artifact_index(context)

        def eligible(info, name):
            marker = info.get("marker")
            return (marker in {"DNP", "SNP"} and info.get("module") == marker.lower() + "-call"
                    and info.get("step_id") in successful_steps and info.get("sample_id") in sample_ids
                    and (name.startswith("full_output_") or name == "SNPcall_output.txt"))

        # A successful step can refer to a table that has since been deleted.
        # Enforce only the file identities actually recorded in older runs.
        for relative, info in artifacts[0].items():
            if eligible(info, PurePosixPath(relative).name):
                self.require_count_table(_scoped(context["run"], relative))
        for entry in self._file_descriptors(run_id, context, artifact_index=artifacts):
            if entry["canonical"] and eligible(entry, entry["name"]):
                path = _scoped(context["run"], entry["relative_path"], file=True)
                self.verify_count_table(path, entry.get("recorded_sha256"))
                yield entry["marker"], entry["sample_id"], path

    def require_count_table(self, path):
        if not path.is_file():
            raise ValueError(_translation((
                f"La tabella dei conteggi {path.name} non è disponibile. Controlla i file dell’esperimento.",
                f"The recorded count table {path.name} is unavailable. Check the experiment files."
            ), self.language))

    def verify_count_table(self, path, digest, size=None):
        """Check the evidence actually recorded for an output or imported count table."""
        changed = type(size) is int and path.stat().st_size != size
        if not changed and digest is not None:
            with path.open("rb") as stream:
                changed = hashlib.file_digest(stream, "sha256").hexdigest() != digest
        if changed:
            raise ValueError(_translation((
                f"La tabella dei conteggi {path.name} è cambiata dopo la verifica dell’esperimento.",
                f"The count table {path.name} has changed since the experiment was verified."
            ), self.language))

    def export_paths(self, run_id) -> list[tuple[Path, str]]:
        """Validate the in-scope files for one export using a single inventory."""
        context = self._context(run_id)
        return [(_scoped(context["run"], item["relative_path"], file=True), item["relative_path"])
                for item in self._file_descriptors(run_id, context)]

    def _file(self, run_id, file_id):
        if not isinstance(file_id, str) or not re.fullmatch(r"[a-f0-9]{32}", file_id):
            raise ValueError("Identificativo del file non valido.")
        run = self._run(run_id)
        descriptor = next((item for item in self._file_descriptors(run_id) if item["id"] == file_id), None)
        if descriptor is None:
            raise ValueError("Il file non appartiene ai risultati dell’esperimento.")
        return _scoped(run, descriptor["relative_path"], file=True), descriptor

    def file_path(self, run_id, file_id) -> Path:
        return self._file(run_id, file_id)[0]

    def file_info(self, run_id, file_id) -> dict:
        return self._file(run_id, file_id)[1]

    def table(self, run_id, file_id, offset=0, limit=100, query="", filters=None) -> dict:
        self._page(offset, limit)
        path, descriptor = self._file(run_id, file_id)
        if descriptor["kind"] != "table":
            raise ValueError("Il risultato selezionato non è una tabella.")
        if not isinstance(query, str) or len(query) > 1000 or not isinstance(filters or {}, dict):
            raise ValueError("Filtri della tabella non validi.")
        filters = filters or {}
        columns = _columns(path)
        if any(k not in columns or not isinstance(v, (str, list)) or isinstance(v, list) and
               (len(v) > 100 or any(not isinstance(x, str) for x in v)) for k, v in filters.items()):
            raise ValueError("Filtro su una colonna non disponibile.")
        snapshot = _signature(path)
        total = matched = 0
        result = []
        row_numbers = []
        needle = query.casefold()
        for row in _rows(path):
            total += 1
            if needle and not any(needle in value.casefold() for value in row.values()):
                continue
            if any(row[key] not in value if isinstance(value, list) else row[key] != value for key, value in filters.items()):
                continue
            if offset <= matched < offset + limit:
                result.append(row)
                row_numbers.append(total - 1)
            matched += 1
        if snapshot != _signature(path):
            raise ValueError("Il risultato è cambiato durante la lettura. Aggiorna la pagina.")
        context = self._context(run_id)
        sample_labels = {s["id"]: s["label"] for s in context["samples"]}
        artifact_index, _ = self._artifact_index(context)
        for item in artifact_index.values():
            if item.get("step_id") == descriptor.get("step_id") and item.get("native_name") and item.get("sample_id"):
                sample_labels[item["native_name"]] = sample_labels.get(item["sample_id"], item["sample_id"])
        if descriptor.get("sample_id"):
            # SNP standalone summaries always name their one internal column sample_0001.
            sample_labels["sample_0001"] = descriptor.get("sample_label") or descriptor["sample_id"]
        return {"file": descriptor, "columns": [column_description(k, language=self.language, samples=sample_labels) for k in columns],
                "rows": result, "row_numbers": row_numbers, "total": total, "matched": matched,
                "offset": offset, "limit": limit, "has_more": offset + limit < matched}

    def curve(self, run_id, file_id) -> dict:
        """Read a complete recorded curve; never reconstruct or truncate values.

        This separate bounded read avoids rescanning large native tables once per
        page. Larger curves remain available through the table and original PDF.
        """
        path, descriptor = self._file(run_id, file_id)
        module = descriptor.get("module")
        if (descriptor["kind"] != "table" or not descriptor["canonical"] or
                module not in {"cpi", "cpin"} or
                not _CPI_CURVE_NAME.search(descriptor["name"])):
            raise ValueError(_translation(("Il risultato selezionato non è una curva CPI prenatale o postnatale.",
                                           "The selected result is not a prenatal or postnatal CPI curve."), self.language))
        too_large = _translation((
            "La curva supera il limite del grafico interattivo. Consulta la tabella completa o il PDF originale.",
            "The curve exceeds the interactive chart limit. Open the full table or original PDF."), self.language)
        snapshot = _signature(path)
        if snapshot[0] > _MAX_CURVE_BYTES:
            raise ValueError(too_large)
        columns = _columns(path)
        x_key, y_key, through_key = (("Iteration", "log_CPI", None) if module == "cpi" else
                                     ("Min_child_reads", "Log10_CPI", "Through_min_child_reads"))
        if not {x_key, y_key, *([through_key] if through_key else [])}.issubset(columns):
            raise ValueError(_translation(("La tabella non contiene le colonne richieste dalla curva.",
                                           "The table does not contain the required curve columns."), self.language))
        rows, size = [], sum(len(column.encode("utf-8")) for column in columns)
        for row in _rows(path):
            size += sum(len(value.encode("utf-8")) for value in row.values())
            if len(rows) >= _MAX_CURVE_ROWS or size > _MAX_CURVE_BYTES:
                raise ValueError(too_large)
            rows.append(row)
        if snapshot != _signature(path):
            raise ValueError(_translation(("La curva è cambiata durante la lettura. Aggiorna la pagina.",
                                           "The curve changed while reading. Refresh the page."), self.language))
        return {"file": descriptor,
                "columns": [column_description(key, language=self.language) for key in columns],
                "rows": rows, "row_numbers": list(range(len(rows))), "total": len(rows), "matched": len(rows),
                "offset": 0, "limit": _MAX_CURVE_ROWS, "has_more": False,
                "curve": {"x_key": x_key, "y_key": y_key, "through_key": through_key,
                          "interval_endpoints": "inclusive" if through_key else None}}

    def _metric(self, key, value):
        result = column_description(key, language=self.language)
        result["value"] = None if value is None or value in MISSING else value
        result["raw_value"] = value
        result["available"] = result["value"] is not None
        return result

    def _summary_metric(self, key, row):
        # The original cell remains available in the detail table even when
        # an imported or incomplete archive contains an inconsistent estimate.
        value = row.get(key)
        metric = self._metric(key, value)
        if not metric["available"]:
            return metric
        try:
            numeric = Decimal(value)
            valid = numeric.is_finite()
            if key in {"informative_sites", "N_sites_mother", "N_sites_father", "N_sites",
                       "Matching_sites", "Mismatching_sites", "No_obligatory_allele_sites"}:
                valid = _read_count(value) is not None
            elif key in {"mean_contamination", "sd_contamination"}:
                count = _read_count(row.get("informative_sites"))
                minimum_sites = 2 if key == "sd_contamination" else 1
                valid = valid and 0 <= numeric <= 1 and count is not None and count >= minimum_sites
            elif key in {"CPI", "Log10_CPI", "CPI_medianFF", "Median_fetal_fraction_percent"}:
                support = {"CPI": ("N_sites",), "Log10_CPI": ("N_sites",),
                           "CPI_medianFF": ("N_sites_mother", "N_sites_father"),
                           "Median_fetal_fraction_percent": ("N_sites_mother",)}[key]
                # Some older summaries omit the count columns. A present entry
                # must record positive support before we highlight its estimate.
                valid = valid and all(_read_count(row[field]) for field in support if field in row)
                if key in {"CPI", "Median_fetal_fraction_percent"}:
                    valid = valid and numeric >= 0
        except (ValueError, TypeError, InvalidOperation):
            valid = False
        if not valid:
            metric.update(value=None, available=False)
        return metric

    def _calling_stats(self, path):
        signature = _signature(path)
        key = (str(path), signature)
        with self._lock:
            if key in self._stats_cache:
                return dict(self._stats_cache[key])
        count = reads = missing_counts = 0
        counts = Counter()
        recognized = "GT" in _columns(path)
        for row in _rows(path):
            count += 1
            genotype = row.get("GT")
            if genotype in {"0/0", "0/1", "1/1"}:
                counts[genotype] += 1
            elif genotype in MISSING:
                counts["unassigned"] += 1
            else:
                recognized = False
            n = _read_count(row.get("total_count"))
            if n is not None:
                reads += n
            else:
                missing_counts += 1
        if signature != _signature(path):
            raise ValueError("La tabella dei genotipi è cambiata durante la lettura.")
        result = {"site_count": count, "assigned": count - counts["unassigned"] if recognized else None,
                  "unassigned": counts["unassigned"] if recognized else None,
                  "read_observations": None if missing_counts else reads,
                  "sites_with_missing_read_counts": missing_counts,
                  "genotype_counts": dict(counts) if recognized else None}
        with self._lock:
            if len(self._stats_cache) >= 256:
                self._stats_cache.pop(next(iter(self._stats_cache)))
            self._stats_cache[key] = result
        return dict(result)

    def overview(self, run_id, module=None, marker=None) -> dict:
        if module is not None and module not in MODULE_LABELS:
            raise ValueError("Analisi dei risultati non riconosciuta.")
        if marker is not None and marker not in {"DNP", "SNP"}:
            raise ValueError("Marcatore dei risultati non riconosciuto.")
        context = self._context(run_id)
        files = self._file_descriptors(run_id, context)
        _, families = self._artifact_index(context)
        samples = {s["id"]: s for s in context["samples"]}
        groups = {}
        step_status = {step["id"]: step["status"] for step in context["steps"]}
        for step in context["steps"]:
            key = step["module"], step["marker"]
            if key[0] not in MODULE_LABELS or module and module != key[0] or marker and marker != key[1]:
                continue
            group = groups.setdefault(key, {"module": key[0], "label": _translation(MODULE_LABELS[key[0]], self.language),
                                           "marker": key[1], "status": step["status"], "steps": [], "entries": [], "warnings": [], "files": []})
            group["steps"].append(step)
            if step["status"] != "succeeded":
                group["status"] = step["status"]
        for key, group in groups.items():
            relevant = [f for f in files if (f.get("module"), f.get("marker")) == key and f["canonical"]]
            group["files"] = relevant
            if key[0] in {"dnp-call", "snp-call"}:
                for f in relevant:
                    if not (f["name"].startswith("full_output_") or f["name"] == "SNPcall_output.txt"):
                        continue
                    try:
                        stats = self._calling_stats(_scoped(context["run"], f["relative_path"], file=True))
                        metrics = [self._metric(k, None if stats[k] is None else str(stats[k]))
                                   for k in ("site_count", "assigned", "unassigned", "read_observations")]
                        genotype_counts = stats["genotype_counts"]
                        distribution = [self._metric(k, str(genotype_counts.get(gt, 0)) if genotype_counts is not None else None)
                                        for k, gt in (("hom_ref", "0/0"), ("heterozygous", "0/1"), ("hom_alt", "1/1"))]
                        group["entries"].append({"sample_id": f.get("sample_id"), "sample_label": f.get("sample_label"),
                            "label": f.get("sample_label") or f["name"], "file_id": f["id"], **stats, "metrics": metrics,
                            "summary": {"kind": "genotypes", "step_status": step_status.get(f.get("step_id")),
                                        "metrics": [*metrics[:3], *distribution]},
                            "plot_file_ids": [p["id"] for p in relevant if p["kind"] == "pdf" and
                                              (p.get("sample_id") == f.get("sample_id") or not p.get("sample_id"))]})
                    except (OSError, ValueError) as exc:
                        group["warnings"].append(str(exc))
                group["matrix_file_ids"] = [f["id"] for f in relevant if f["name"] in {"output_AllGenotypes.txt", "SNPcall_AllGenotypes.txt", "merged_genotypes.tsv"}]
                continue
            name = {"contamination": "contamination_summary.txt", "cpi": "Summary_FetalFraction_CPI.csv", "cpin": "Summary_Postnatal_CPI.txt"}[key[0]]
            prefixes = {step["id"]: step["output_prefix"] for step in group["steps"]}
            guides = {f["step_id"]: _cpi_guides(context["run"], f, key[0]) for f in relevant
                      if key[0] in {"cpi", "cpin"} and f.get("step_id") in prefixes and step_status[f["step_id"]] == "succeeded"
                      and f["relative_path"] == prefixes[f["step_id"]] + "scientific-settings.json"}
            for summary in (f for f in relevant if f.get("step_id") in prefixes
                            and f["relative_path"] == prefixes[f["step_id"]] + name):
                try:
                    count = 0
                    for count, row in enumerate(_rows(_scoped(context["run"], summary["relative_path"], file=True)), 1):
                        if count > _MAX_SUMMARY:
                            group["warnings"].append("Riepilogo limitato a 10000 righe; tutte le righe restano consultabili nella tabella originale.")
                            break
                        entry = {"file_id": summary["id"], "row": row, "row_number": count - 1, "metrics": [],
                                 "step_id": summary.get("step_id"), "curve_file_ids": [], "plot_file_ids": []}
                        if key[0] == "contamination":
                            table = next((f for f in relevant if f.get("step_id") == summary.get("step_id") and
                                          f.get("native_name") == row.get("individuo") and f["name"].startswith("contamination_") and f["name"] != name), None)
                            sample_id = table.get("sample_id") if table else row.get("individuo")
                            entry.update(sample_id=sample_id, sample_label=samples.get(sample_id, {}).get("label", sample_id),
                                         label=samples.get(sample_id, {}).get("label", sample_id), site_file_id=table["id"] if table else None)
                            metric_keys = ["mean_contamination", "sd_contamination", "informative_sites"]
                        else:
                            native = row.get("Pair" if key[0] == "cpi" else "Trio")
                            family = next((f for f in families if f["native_id"] == native and f["step_id"] == summary.get("step_id")), None)
                            family_id = family["id"] if family else native
                            analysis = row.get("Analysis")
                            entry.update(family_id=family_id, family_label=self._family_label(family, samples),
                                         label=self._family_label(family, samples) or family_id, analysis=analysis,
                                         native_family=native, cutoff=row.get("Cutoff"))
                            related = [f for f in relevant if f.get("step_id") == summary.get("step_id") and f.get("family_id") == family_id]
                            entry["curve_file_ids"] = [f["id"] for f in related if f["kind"] == "table" and
                                                        _CPI_CURVE_NAME.search(f["name"]) and
                                                        (not analysis or f.get("analysis") == analysis) and
                                                        (key[0] != "cpi" or f.get("cutoff") == row.get("Cutoff"))]
                            entry["plot_file_ids"] = [f["id"] for f in related if f["kind"] == "pdf" and
                                                       (not analysis or f.get("analysis") == analysis)]
                            site = next((f for f in related if f["name"].endswith(("_sites.tsv", "_sites.txt"))), None)
                            entry["site_file_id"] = site["id"] if site else None
                            if key[0] == "cpi":
                                counts = [f["paternal_used_at_median"] for f in related
                                          if f["id"] in entry["curve_file_ids"] and "paternal_used_at_median" in f]
                                if len(counts) == 1:
                                    row["paternal_used_at_median"] = str(counts[0])
                            metric_keys = (["Median_fetal_fraction_percent", "CPI_medianFF", "N_sites_mother", "N_sites_father"]
                                           if key[0] == "cpi" else ["CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"])
                        if key[0] == "cpin" and "No_obligatory_allele_sites" in row:
                            metric_keys.append("No_obligatory_allele_sites")
                        if "paternal_used_at_median" in row and key[0] == "cpi":
                            metric_keys.append("paternal_used_at_median")
                        if count == 1:
                            group.setdefault("summary_columns", {}).update(
                                (k, column_description(k, language=self.language)) for k in row)
                        entry["metrics"] = [self._metric(k, row.get(k)) for k in metric_keys]
                        summary_keys = (("CPI_medianFF", *metric_keys[2:], "Median_fetal_fraction_percent")
                                        if key[0] == "cpi" else metric_keys)
                        entry["summary"] = {
                            "kind": {"cpi": "prenatal_cpi", "cpin": "postnatal_cpi", "contamination": "contamination"}[key[0]],
                            "step_status": step_status.get(summary.get("step_id")),
                            "metrics": [self._summary_metric(field, row) for field in summary_keys],
                        }
                        if key[0] == "cpi" or key[0] == "cpin" and "Mismatch_probability" in row:
                            entry["summary"]["guide_band"] = _reported_cpi_band(
                                row, guides.get(summary.get("step_id")), key[1], key[0])
                        group["entries"].append(entry)
                    group["summary_truncated"] = group.get("summary_truncated", False) or count > _MAX_SUMMARY
                except (OSError, ValueError) as exc:
                    group["warnings"].append(str(exc))
        return {"run_id": run_id, "modules": list(groups.values()), "warnings": context["warnings"],
                "not_run": [m for m in MODULE_LABELS if m not in {s["module"] for s in context["steps"]}],
                "interpretation": {k: _translation(text, self.language) for k, text in {
                    "missing": ("NA indica un valore non disponibile; non equivale a zero.", "NA indicates an unavailable value; it is not zero."),
                    "read_observations": ("Somma delle osservazioni dei siti, non conteggio di letture uniche.", "Sum of observations across sites, not a count of unique reads."),
                    "curve_intervals": ("Gli estremi degli intervalli della curva del CPI postnatale sono inclusi.", "Postnatal CPI curve interval endpoints are inclusive."),
                    "technical_status": ("Il completamento dell’esecuzione non è una validazione clinica.", "Successful execution is not clinical validation.")}.items()}}
