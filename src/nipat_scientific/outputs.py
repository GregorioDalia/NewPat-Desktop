"""Scientific output contracts shared by individual requests and workflow plans."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import sys

from nipat_scientific.errors import PlanExecutionError, ValidationError
from nipat_scientific.files import (
    DNP_OUTPUT_COLUMNS, locus_key, nonnegative_integer, require_columns,
    require_dnp_input, table_rows, tabular_header,
)
from nipat_scientific.panels import read_dnp_list, read_snp_list
from nipat_scientific.settings import GENOTYPE_COMBINATIONS, normalize_settings, validate_settings_document


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


_CPI_COLUMNS = {
    "Pair", "N_sites_mother", "N_sites_father", "Median_fetal_fraction_raw",
    "Median_fetal_fraction_percent", "Max_logCPI", "Min_logCPI",
    "Median_logCPI", "Mean_logCPI", "CPI_medianFF", "Error_constant", "Min_fetal_reads", "Min_fetal_percent", "Marker_type",
}
_SNP_COLUMNS = {
    "chr", "pos", "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count", "ratio",
    "GL0", "GL1", "GL2", "GT", "reads_discarded_for_indels",
    "ratio_reads_discarded_for_indels", "combined_bases", "combined_counts",
}
_DNP_LOCI = {"chr", "pos1", "pos2", "REF", "ALT"}


def _artifact(path: Path, root: Path, output_dir: Path) -> dict:
    resolved_output = output_dir.resolve()
    if (path.is_symlink() or not path.is_file() or not resolved_output.is_relative_to(root.resolve())
            or not path.resolve().is_relative_to(resolved_output)):
        raise PlanExecutionError("execution.output", f"Expected output is missing or outside its directory: {path.name}")
    return {"path": path.relative_to(root).as_posix(), "sha256": _sha256(path)}


def _output_columns(path: Path, columns: set[str]) -> None:
    try:
        require_columns(path, columns, "Invalid scientific result")
    except ValidationError as exc:
        raise PlanExecutionError("execution.output", str(exc)) from exc


def _cpi_bindings(step: dict) -> tuple[list[dict], list[dict]]:
    """Assign controlled aliases by typed identity, never by biological guesswork."""
    aliases = {}
    inputs, pairs = [], []
    for pair in step["inputs"]["pairs"]:
        names = {}
        for role, prefix in (("mother", "Mother"), ("father", "Father")):
            reference = pair[role]
            key = (reference.get("step"), reference["sample"])
            if key not in aliases:
                native = f"s{len(aliases) + 1:04d}"
                aliases[key] = native
                inputs.append({"source": reference.copy(), "name": f"{prefix}{native}.txt"})
            names[role] = aliases[key]
        pairs.append({
            "pair": pair["id"], "mother": pair["mother"].copy(), "father": pair["father"].copy(),
            "native_pair": f"Mother{names['mother']}-Father{names['father']}_{step.get('parameters', {}).get('marker_type', 'DNP')}s",
            "native_selection": f"{names['mother']}:{names['father']}",
        })
    return inputs, pairs



def _cpin_bindings(step: dict) -> tuple[list[dict], list[dict]]:
    aliases, inputs, trios = {}, [], []
    marker = step.get("parameters", {}).get("marker_type", "DNP")
    for trio in step["inputs"]["trios"]:
        names = {}
        for role in ("mother", "father", "child"):
            ref = trio[role]
            key = (ref.get("step"), ref["sample"])
            if key not in aliases:
                native = f"s{len(aliases) + 1:04d}"
                aliases[key] = native
                inputs.append({"source": ref.copy(), "name": f"{role.title()}{native}.txt"})
            names[role] = aliases[key]
        trios.append({"trio": trio["id"], **{role: trio[role].copy() for role in names},
                      "native_trio": f"Mother{names['mother']}-Father{names['father']}-Child{names['child']}_{marker}s",
                      "native_selection": ":".join(names.values())})
    return inputs, trios


def _expected_settings(request: dict) -> dict:
    values = normalize_settings(request["workflow"], request.get("scientific_settings"))
    if request["workflow"] == "cpi" and request.get("err_const") is not None:
        values[f"err_const_{request.get('marker_type', 'DNP').lower()}"] = request["err_const"]
    return values


def _check_cpi_summary_settings(row: dict, request: dict, settings: dict, path: Path, number: int):
    marker = request.get("marker_type", "DNP")
    if row["Marker_type"] != marker:
        raise PlanExecutionError("execution.output", "CPI summary marker differs from the request.")
    if request["workflow"] == "cpin":
        numeric = {"Min_coverage": settings["min_coverage"],
                   "Mismatch_probability": settings[f"mismatch_probability_{marker.lower()}"]}
        for pair in GENOTYPE_COMBINATIONS:
            if row[f"Include_{pair}"] != str(settings[f"include_{pair}"]).upper():
                raise PlanExecutionError("execution.output", "Postnatal site selection differs from the request.")
    else:
        numeric = {"Min_fetal_reads": settings["min_fetal_reads"], "Min_fetal_percent": settings["min_fetal_percent"],
                   "Error_constant": settings[f"err_const_{marker.lower()}"]}
    for column, expected in numeric.items():
        raw = row[column]
        if expected is None:
            agrees = raw == "NA"
        else:
            try:
                agrees = math.isclose(float(raw), expected, rel_tol=1e-12)
            except ValueError:
                agrees = False
        if not agrees:
            raise PlanExecutionError("execution.output", f"{path.name}: row {number}, {column} differs from the request.")


def _verify_postnatal_sites(path: Path, summary: dict, counts: dict) -> None:
    """Reconcile the one trio estimate against its selected, eligible site rows."""
    columns = {"Status", "Genotype_combination", "Paternity_status", "Paternity_Index", "Mismatch",
               "Required_paternal_allele", "Paternal_transmission", "Ref_f.pop", "Alt_f.pop"}
    observed = dict.fromkeys(counts, 0)

    def site_logs():
        for line, site in table_rows(path, columns, "Postnatal CPI sites"):
            if site["Status"] == "mother_child_incompatible":
                observed["Maternal_incompatible_sites"] += 1
            if site["Status"] != "eligible":
                if site["Paternity_Index"] != "NA" or site["Paternity_status"] != "NA":
                    raise PlanExecutionError("execution.output", f"{path.name}: excluded site with PI at row {line}.")
                continue
            group, status = site["Genotype_combination"], site["Paternity_status"]
            if group not in GENOTYPE_COMBINATIONS or summary[f"Include_{group}"] != "TRUE":
                raise PlanExecutionError("execution.output", f"{path.name}: unexpected genotype group at row {line}.")
            if group == "het_het":
                valid = status == "no_obligatory_allele" and site["Mismatch"] == "NA"
            else:
                valid = (status, site["Mismatch"]) in {("match", "FALSE"), ("mismatch", "TRUE")}
            if not valid:
                raise PlanExecutionError("execution.output", f"{path.name}: inconsistent paternal status at row {line}.")
            observed["N_sites"] += 1
            observed["N_" + group] += 1
            observed[{"match": "Matching_sites", "mismatch": "Mismatching_sites",
                      "no_obligatory_allele": "No_obligatory_allele_sites"}[status]] += 1
            try:
                pi = float(site["Paternity_Index"])
            except ValueError as exc:
                raise PlanExecutionError("execution.output", f"{path.name}: invalid PI at row {line}.") from exc
            if not pi > 0:
                raise PlanExecutionError("execution.output", f"{path.name}: non-positive or missing PI at row {line}.")
            if math.isfinite(pi):
                yield math.log10(pi)
                continue
            # The native log sum preserves the finite estimate when the per-site
            # ratio itself overflows. Reconstruct that term from its operands.
            try:
                if group == "het_het":
                    weight = 1.0
                    frequency = float(site["Ref_f.pop"]) + float(site["Alt_f.pop"])
                else:
                    allele = {"REF": "Ref_f.pop", "ALT": "Alt_f.pop"}[site["Required_paternal_allele"]]
                    frequency = float(site[allele])
                    weight = float(summary["Mismatch_probability"] if status == "mismatch" else site["Paternal_transmission"])
                if not 0 < frequency <= 2 or not 0 < weight <= 1:
                    raise ValueError
                log_pi = math.log10(weight) - math.log10(frequency)
                # The denominator in the table is itself rounded for export.
                if log_pi < math.log10(sys.float_info.max) - 1e-12:
                    raise ValueError
                yield log_pi
            except (KeyError, ValueError) as exc:
                raise PlanExecutionError("execution.output", f"{path.name}: inconsistent overflowing PI at row {line}.") from exc

    log_cpi = math.fsum(site_logs())
    if counts != observed:
        raise PlanExecutionError("execution.output", f"{path.name}: site counts differ from the trio summary.")
    if not counts["N_sites"]:
        if (summary["CPI"], summary["Log10_CPI"]) != ("NA", "NA"):
            raise PlanExecutionError("execution.output", "Postnatal CPI without contributing sites.")
        return
    # The native text tables round individual floating-point values for export.
    tolerance = 2e-14 * counts["N_sites"]
    try:
        published = float(summary["Log10_CPI"])
        raw = float(summary["CPI"])
    except ValueError as exc:
        raise PlanExecutionError("execution.output", "Invalid postnatal trio CPI.") from exc
    if not math.isclose(published, log_cpi, abs_tol=tolerance, rel_tol=5e-14):
        raise PlanExecutionError("execution.output", "Postnatal log10(CPI) disagrees with the eligible site indices.")
    # A raw product can overflow or underflow while the log sum remains usable.
    if raw == 0:
        consistent = published <= math.log10(math.ulp(0.0)) - math.log10(2) + tolerance
    elif raw == math.inf:
        consistent = published >= math.log10(sys.float_info.max) - tolerance
    elif math.isfinite(raw) and raw > 0:
        quantization = math.log10(1 + math.ulp(raw) / raw)
        consistent = math.isclose(math.log10(raw), published, abs_tol=max(quantization, tolerance), rel_tol=5e-14)
    else:
        consistent = False
    if not consistent:
        raise PlanExecutionError("execution.output", "Postnatal CPI and log10(CPI) disagree.")


def _collect_cpin_outputs(step: dict, request: dict, root: Path, output_dir: Path) -> dict:
    summary = output_dir / "Summary_Postnatal_CPI.txt"
    summary_artifact = _artifact(summary, root, output_dir)
    count_columns = {"N_sites", "Matching_sites", "Mismatching_sites", "No_obligatory_allele_sites",
                     "Maternal_incompatible_sites", *("N_" + pair for pair in GENOTYPE_COMBINATIONS)}
    columns = count_columns | {"Trio", "Marker_type", "Log10_CPI", "CPI", "Mismatch_probability", "Min_coverage",
                               *("Include_" + pair for pair in GENOTYPE_COMBINATIONS)}
    bindings = step.get("native_bindings")
    if bindings is None:
        _, bindings = _cpin_bindings(step)
    expected = {binding["native_trio"] for binding in bindings}
    rows = {}
    warnings = []
    settings = _expected_settings(request)
    for number, row in table_rows(summary, columns, "Postnatal CPI summary"):
        name = row["Trio"]
        if name not in expected or name in rows:
            raise PlanExecutionError("execution.output", "Unexpected or duplicate postnatal CPI trio row.")
        _check_cpi_summary_settings(row, request, settings, summary, number)
        counts = {key: nonnegative_integer(row[key], summary, number, key) for key in count_columns}
        rows[name] = row, counts
        warnings.extend(_numeric_warnings(row, {"Log10_CPI", "CPI"}, summary, number,
                                         allow_missing=counts["N_sites"] == 0))
    if rows.keys() != expected:
        raise PlanExecutionError("execution.output", "Postnatal CPI results do not match the requested trios.")
    trios = []
    for binding in bindings:
        name = binding["native_trio"]
        path = output_dir / f"{name}_sites.txt"
        artifact = _artifact(path, root, output_dir)
        _verify_postnatal_sites(path, *rows[name])
        trios.append({**binding, "sites": artifact})
    return {"summary": summary_artifact, "cpin-trios": trios, "quality_warnings": warnings}


def _pdf_artifact(path: Path, root: Path, output_dir: Path) -> dict:
    artifact = _artifact(path, root, output_dir)
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-" or path.stat().st_size <= 5:
            raise PlanExecutionError("execution.output", f"Invalid scientific PDF: {path.name}")
    return artifact


def _collect_snp_auxiliary(output_dir: Path, root: Path, genotypes: dict) -> dict:
    """Require the complete SNPcall 2.0 result, including native summaries."""
    summary = output_dir / "summary"
    table = summary / "SNPcall_AllGenotypes.txt"
    genotype_artifact = _artifact(table, root, output_dir)
    actual = {}
    for number, row in table_rows(table, {"chr", "pos", "REF", "ALT", "GT_sample_0001"}, "SNP genotypes"):
        key = (row["chr"], nonnegative_integer(row["pos"], table, number, "pos", positive=True))
        if key in actual:
            raise PlanExecutionError("execution.output", "SNP genotype summary contains duplicate loci.")
        actual[key] = (row["REF"], row["ALT"], row["GT_sample_0001"])
    if actual != genotypes:
        raise PlanExecutionError("execution.output", "SNP genotype summary differs from its sample result.")
    resource_path = summary / "resources.tsv"
    resource_artifact = _artifact(resource_path, root, output_dir)
    resources = list(table_rows(resource_path, {"sample", "seconds", "resident_MB_start", "resident_MB_end"},
                                "SNP resources"))
    if len(resources) != 1 or resources[0][1]["sample"] != "sample_0001":
        raise PlanExecutionError("execution.output", "SNP resource summary must contain the native sample exactly once.")
    _, resource = resources[0]
    for column in ("seconds", "resident_MB_start", "resident_MB_end"):
        raw = resource[column]
        if raw == "NA" and column != "seconds":
            continue
        try:
            value = float(raw)
        except ValueError as exc:
            raise PlanExecutionError("execution.output", f"Invalid SNP resource value: {column}") from exc
        if not math.isfinite(value) or value < 0:
            raise PlanExecutionError("execution.output", f"Invalid SNP resource value: {column}")
    plots = [_pdf_artifact(output_dir / "plots" / "sample_0001" / f"sample_0001_{name}.pdf", root, output_dir)
             for name in ("N_genotypes", "Ref_read_count", "Alt_read_count", "Other_read_count")]
    plots.append(_pdf_artifact(summary / "Unassigned_genotypes.pdf", root, output_dir))
    return {"genotypes": genotype_artifact, "resources": resource_artifact, "plots": plots}


def _dnp_genotypes(output_dir: Path, root: Path, sample_names: list[str], loci: dict) -> tuple[dict, dict]:
    path = output_dir / "summary" / "output_AllGenotypes.txt"
    artifact = _artifact(path, root, output_dir)
    genotype_columns = [f"GT_{sample}" for sample in sample_names]
    columns = _DNP_LOCI | set(genotype_columns)
    if set(tabular_header(path)) != columns:
        raise PlanExecutionError("execution.output", "DNP genotype summary columns differ from the selected samples.")
    genotypes = {}
    for line, row in table_rows(path, columns, "DNP genotype summary"):
        key = locus_key(row, path, line, "DNP")
        if key in genotypes:
            raise PlanExecutionError("execution.output", "DNP genotype summary contains duplicate loci.")
        if loci.get(key) != (row["REF"], row["ALT"]):
            raise PlanExecutionError("execution.output", "DNP genotype summary loci or alleles differ from the panel.")
        genotypes[key] = tuple(row[column] for column in genotype_columns)
    if genotypes.keys() != loci.keys():
        raise PlanExecutionError("execution.output", "DNP genotype summary loci differ from the panel.")
    return artifact, genotypes


def _prenatal_curve_support(curve: Path, summary: dict, cutoff: str) -> dict:
    """Validate the dense native curve and recover support for the reported estimate."""
    counts = ("InfSites_mother", "InfSites_father", "Mismatch", "NotMismatch")
    columns = {"Iteration", *counts, "CPI", "log_CPI", "Cutoff"}
    reads = summary["Min_fetal_reads"]
    minimum = 1 if reads == "NA" else int(float(reads))
    maternal = nonnegative_integer(summary["N_sites_mother"], curve, 1, "N_sites_mother")
    candidates = nonnegative_integer(summary["N_sites_father"], curve, 1, "N_sites_father")
    if candidates > maternal:
        raise PlanExecutionError("execution.output", f"{curve.name}: paternal candidates exceed maternal sites.")
    support = {"minimum_fetal_reads": None if reads == "NA" else minimum, "paternal_candidates": candidates,
               "paternal_used": 0, "missing_frequency": 0, "unassigned_father": 0,
               "median_fetal_reads": None, "paternal_used_at_median": 0}
    previous = previous_log = None
    lower = upper = None
    for offset, (number, row) in enumerate(table_rows(curve, columns, "Prenatal CPI curve")):
        threshold = nonnegative_integer(row["Iteration"], curve, number, "Iteration")
        values = tuple(nonnegative_integer(row[key], curve, number, key) for key in counts)
        mother, father, mismatch, no_mismatch = values
        with_frequency = mismatch + no_mismatch
        if (threshold != minimum + offset or row["Cutoff"] != cutoff or mother == 0
                or not mismatch <= father <= with_frequency <= min(mother, candidates)
                or (previous is not None and any(now > before for now, before in zip(values, previous)))):
            raise PlanExecutionError("execution.output", f"{curve.name}: inconsistent counts, cutoff or threshold at row {number}.")
        if previous is None:
            if mother != maternal:
                raise PlanExecutionError("execution.output", f"{curve.name}: maternal count differs from summary.")
            support.update(paternal_used=father, missing_frequency=candidates - with_frequency,
                           unassigned_father=with_frequency - father)
        log_value = None
        if father:
            try:
                raw, log_value = float(row["CPI"]), float(row["log_CPI"])
            except ValueError as exc:
                raise PlanExecutionError("execution.output", f"{curve.name}: invalid CPI at row {number}.") from exc
            # Exponentiation may legitimately underflow to zero or overflow to Inf.
            if math.isnan(raw) or raw < 0 or not math.isfinite(log_value):
                raise PlanExecutionError("execution.output", f"{curve.name}: invalid CPI at row {number}.")
        elif (row["CPI"], row["log_CPI"]) != ("NA", "NA"):
            raise PlanExecutionError("execution.output", f"{curve.name}: CPI without a contributing site at row {number}.")
        if previous is not None and father == previous[1] and log_value != previous_log:
            raise PlanExecutionError("execution.output", f"{curve.name}: log CPI changed with the same contributing sites at row {number}.")
        # Site support is an integer. Its two central observations are the last
        # thresholds retaining respectively more than and at least half the loci.
        if 2 * mother > maternal:
            lower = threshold, father, log_value
        if 2 * mother >= maternal:
            upper = threshold, father, log_value
        previous, previous_log = values, log_value
    if maternal and lower is None:
        raise PlanExecutionError("execution.output", f"{curve.name}: missing curve for informative maternal sites.")
    median_log = None
    if lower is not None:
        middle = round((lower[0] + upper[0]) / 2)
        # With even N there are no loci with support between the central two.
        # Above the lower endpoint every row through the upper one has the same sites.
        _, used, median_log = lower if middle == lower[0] else upper
        support.update(median_fetal_reads=middle, paternal_used_at_median=used)
    reported = summary["CPI_medianFF"]
    if median_log is None:
        agrees = reported == "NA"
    else:
        try:
            # R publishes the summary rounded to three decimals; the curve retains
            # the unrounded log with R's usual text serialization precision.
            agrees = math.isclose(float(reported), median_log, abs_tol=0.000500000001, rel_tol=5e-15)
        except ValueError:
            agrees = False
    if not agrees:
        raise PlanExecutionError("execution.output", f"{curve.name}: median-threshold log CPI differs from the summary.")
    return support


def _collect_cpi_outputs(step: dict, request: dict, root: Path, output_dir: Path) -> dict:
    summary = output_dir / "Summary_FetalFraction_CPI.csv"
    artifact = _artifact(summary, root, output_dir)
    mode = request["cutoff_mode"]
    with summary.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        columns = reader.fieldnames or []
        required = _CPI_COLUMNS | ({"Cutoff"} if mode != "all" else set())
        if (not required.issubset(columns) or len(columns) != len(set(columns))
                or (mode == "all" and "Cutoff" in columns)):
            raise PlanExecutionError("execution.output", "CPI summary columns do not match the requested cutoff mode.")
        rows = list(reader)
    if "native_bindings" in step:
        bindings = step["native_bindings"]
    else:
        _, bindings = _cpi_bindings(step)
    cutoffs = ([None] if mode == "all" else [str(Path(request["work_dir"]) / f"{request.get('marker_type', 'DNP')}panel.txt")]
               if mode == "panel" else [panel["label"] for panel in request["cutoffs"]])
    expected = {(pair["native_pair"], cutoff) for pair in bindings for cutoff in cutoffs}
    found = {}
    warnings = []
    settings = _expected_settings(request)
    for number, row in enumerate(rows, 1):
        if None in row or any(value is None for value in row.values()):
            raise PlanExecutionError("execution.output", "Malformed CPI summary row.")
        _check_cpi_summary_settings(row, request, settings, summary, number + 1)
        key = (row["Pair"], row.get("Cutoff"))
        if key in found:
            raise PlanExecutionError("execution.output", "CPI summary contains duplicate pair/cutoff rows.")
        found[key] = number
    if set(found) != expected:
        raise PlanExecutionError("execution.output", "CPI summary does not match the declared pairs and cutoffs.")
    plots = output_dir / "plots"
    expected_plots = {"All_CPIplots.pdf", *(f"{pair['native_pair']}_CPIplot.pdf" for pair in bindings)}
    if {path.name for path in plots.glob("*.pdf")} != expected_plots:
        raise PlanExecutionError("execution.output", "CPI plots do not match the declared pair identities.")
    curves = output_dir / "curves"
    expected_curves = set()
    pairs = []
    for pair in bindings:
        curves_for_pair = []
        for index, cutoff in enumerate(cutoffs, 1):
            curve = curves / f"{pair['native_pair']}_panel_{index}.tsv"
            expected_curves.add(curve.name)
            curve_artifact = _artifact(curve, root, output_dir)
            number = found[(pair["native_pair"], cutoff)]
            row = rows[number - 1]
            support = _prenatal_curve_support(curve, row, cutoff if cutoff is not None else "ALL")
            curves_for_pair.append({"cutoff": cutoff, "prenatal_support": support, **curve_artifact})
            context = {"Pair": pair["native_pair"], "Cutoff": cutoff or "ALL"}
            for field, reason in (("missing_frequency", "no population frequency"),
                                  ("unassigned_father", "unassigned paternal genotype")):
                if support[field]:
                    warnings.append({"code": f"output.cpi_{field}", "file": curve.name, "row": 2,
                                     "column": "InfSites_father", "value": str(support[field]), "context": context,
                                     "message": f"{support[field]} paternal candidate site(s) excluded at the minimum fetal read threshold: {reason}."})
            fetal = {"Median_fetal_fraction_raw", "Median_fetal_fraction_percent"}
            log_stats = {"Max_logCPI", "Min_logCPI", "Median_logCPI", "Mean_logCPI"}
            for fields, used in ((fetal, support["median_fetal_reads"] is not None), (log_stats, support["paternal_used"]),
                                 ({"CPI_medianFF"}, support["paternal_used_at_median"])):
                warnings.extend(_numeric_warnings(row, fields, summary, number + 1, allow_missing=not used))
        pairs.append({
            "pair": pair["pair"], "mother": pair["mother"], "father": pair["father"],
            "native_pair": pair["native_pair"],
            "summary_rows": [{"row": found[(pair["native_pair"], cutoff)], "cutoff": cutoff} for cutoff in cutoffs],
            "plot": _pdf_artifact(plots / f"{pair['native_pair']}_CPIplot.pdf", root, output_dir),
            "curves": curves_for_pair,
        })
    if {path.name for path in curves.glob("*.tsv")} != expected_curves:
        raise PlanExecutionError("execution.output", "CPI curves do not match the declared pairs and cutoffs.")
    return {"summary": artifact, "cpi-pairs": pairs, "quality_warnings": warnings,
            "combined-plot": _pdf_artifact(plots / "All_CPIplots.pdf", root, output_dir)}


def _numeric_warnings(row: dict, columns: set[str], path: Path, number: int, *, allow_missing: bool) -> list[dict]:
    warnings = []
    context = {key: row[key] for key in ("chr", "pos", "pos1", "pos2", "Pair", "Trio", "Analysis", "Cutoff", "individuo") if key in row}
    for column in sorted(columns):
        raw = row[column].strip()
        if raw == "NA" and allow_missing:
            continue
        if raw == "NA":
            warnings.append({"code": "output.missing_estimate", "file": path.name, "row": number,
                             "column": column, "value": raw, "context": context,
                             "message": "Missing scientific estimate despite informative input; inspect the R result and model conditions."})
            continue
        try:
            number_value = float(raw)
        except ValueError as exc:
            raise PlanExecutionError("execution.output", f"{path.name}: row {number}, {column} is not numeric.") from exc
        if not math.isfinite(number_value):
            warnings.append({"code": "output.nonfinite", "file": path.name, "row": number,
                             "column": column, "value": raw, "context": context,
                             "message": "Non-finite scientific result; interpretation requires domain review. The R value is unchanged."})
    return warnings


def _collect_outputs_unchecked(step: dict, request: dict, root: Path, output_dir: Path) -> dict:
    if step["workflow"] == "cpin":
        return _collect_cpin_outputs(step, request, root, output_dir)
    if step["workflow"] == "cpi":
        return _collect_cpi_outputs(step, request, root, output_dir)
    if step["workflow"] == "snp-call":
        path = output_dir / "SNPcall_output.txt"
        artifact = _artifact(path, root, output_dir)
        expected = {(record.chromosome, record.position): record for record in
                    read_snp_list(Path(request["panel"]))}
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t", strict=True)
            columns = reader.fieldnames or []
            if not _SNP_COLUMNS.issubset(columns) or len(columns) != len(set(columns)):
                raise PlanExecutionError("execution.output", "SNPcall result columns are missing or duplicated.")
            found = set()
            genotypes = {}
            warnings = []
            for number, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise PlanExecutionError("execution.output", "Malformed SNPcall result row.")
                try:
                    key = row["chr"], int(row["pos"])
                except ValueError as exc:
                    raise PlanExecutionError("execution.output", "Invalid SNPcall result coordinate.") from exc
                if key in found:
                    raise PlanExecutionError("execution.output", "SNPcall result contains duplicate loci.")
                found.add(key)
                genotypes[key] = (row["REF"], row["ALT"], row["GT"])
                panel_record = expected.get(key)
                if panel_record is None or (row["REF"], row["ALT"]) != (
                        panel_record.reference, panel_record.alternative):
                    raise PlanExecutionError("execution.output", "SNPcall result alleles or loci differ from the selected panel.")
                counts = [nonnegative_integer(row[column], path, number, column)
                          for column in ("N_REF", "N_ALT", "N_Other")]
                if nonnegative_integer(row["total_count"], path, number, "total_count") != sum(counts):
                    raise PlanExecutionError("execution.output", "SNPcall total_count does not equal the read-count sum.")
                warnings.extend(_numeric_warnings(row, {"ratio"}, path, number, allow_missing=sum(counts[:2]) == 0))
                for column in ("GL0", "GL1", "GL2"):
                    if row[column] == "NA":
                        warnings.extend(_numeric_warnings(row, {column}, path, number,
                                                          allow_missing=sum(counts[:2]) == 0))
                        continue
                    try:
                        likelihood = float(row[column])
                    except ValueError as exc:
                        raise PlanExecutionError("execution.output", f"Invalid SNPcall {column}.") from exc
                    # Q=0 legitimately produces log(0) = -Inf in this model.
                    if math.isnan(likelihood) or likelihood == math.inf:
                        raise PlanExecutionError("execution.output", f"Invalid SNPcall {column}: NaN or +Inf.")
                if row["GT"] not in {"NA", "0/0", "0/1", "1/1"}:
                    raise PlanExecutionError("execution.output", "SNPcall genotype must be 0/0, 0/1, 1/1 or NA.")
                if ((not sum(counts[:2]) or counts[2] / sum(counts) >= request.get("scientific_settings", {}).get("other_fraction_max", 0.1)) and row["GT"] != "NA"):
                    raise PlanExecutionError("execution.output", "SNPcall genotype violates the unassigned-genotype rule.")
                if row["reads_discarded_for_indels"] != "NA":
                    nonnegative_integer(row["reads_discarded_for_indels"], path, number,
                                        "reads_discarded_for_indels")
                warnings.extend(_numeric_warnings(row, {"ratio_reads_discarded_for_indels"},
                                                  path, number, allow_missing=True))
        # R outer-joins the selected panel, retaining zero-coverage loci. A
        # header-only file is therefore incomplete for every valid panel.
        if found != set(expected):
            raise PlanExecutionError("execution.output", "SNPcall result loci do not match the selected panel.")
        preparation = []
        if request["mode"] == "bam":
            work = Path(request["work_dir"])
            preparation = [{"kind": kind, **_artifact(work / name, root, work)}
                           for kind, name in (("regions-bed", "snp_regions.bed"), ("pileup", "pileup.txt"))]
        return {"snp-tables": [{"sample": step["inputs"]["sample"], **artifact}],
                "snp-summary": _collect_snp_auxiliary(output_dir, root, genotypes),
                "preparation": preparation, "quality_warnings": warnings}
    if step["workflow"] == "dnp-call":
        directory = output_dir / "individual_outputs"
        expected = {f"full_output_sample_{number:04d}.txt" for number in range(1, len(request["samples"]) + 1)}
        actual = {path.name for path in directory.glob("full_output_*.txt")}
        if expected != actual:
            raise PlanExecutionError("execution.output", f"{step['id']}: DNP tables do not match the declared sample identities.")
        tables = []
        all_warnings = []
        expected_loci = {(row.chromosome, row.pos1, row.pos2): (row.reference, row.alternative)
                         for row in read_dnp_list(Path(request["panel"]))}
        sample_names = [item["sample_id"] for item in request["samples"]]
        summary, genotypes = _dnp_genotypes(output_dir, root, sample_names, expected_loci)
        columns = DNP_OUTPUT_COLUMNS | {"GT"}
        for index, (identifier, name) in enumerate(zip(step["inputs"]["samples"], sample_names, strict=True)):
            path = directory / f"full_output_{name}.txt"
            artifact = _artifact(path, root, output_dir)
            warnings = require_dnp_input(path)
            seen = set()
            for line, row in table_rows(path, columns, "DNPcall output"):
                key = locus_key(row, path, line, "DNP")
                if expected_loci.get(key) != (row["REF"], row["ALT"]):
                    raise PlanExecutionError("execution.output", "DNPcall result loci or alleles do not match the selected panel.")
                if row["GT"] != genotypes[key][index]:
                    raise PlanExecutionError("execution.output", f"DNP genotype summary differs from sample {name}.")
                seen.add(key)
            if seen != expected_loci.keys():
                raise PlanExecutionError("execution.output", "DNPcall result loci or alleles do not match the selected panel.")
            all_warnings.extend({**warning, "code": warning["code"].replace("input.", "output.", 1)}
                                for warning in warnings)
            tables.append({"sample": identifier, "native_name": name, **artifact})
        return {"dnp-tables": tables, "dnp-summary": {"genotypes": summary},
                "quality_warnings": all_warnings}

    summary = output_dir / "contamination_summary.txt"
    artifact = _artifact(summary, root, output_dir)
    _output_columns(summary, {"individuo", "informative_sites", "mean_contamination", "sd_contamination"})
    rows = [row for _, row in table_rows(summary, {
        "individuo", "informative_sites", "mean_contamination", "sd_contamination",
    }, "Contamination summary")]
    expected_names = [Path(sample["name"]).stem for sample in request["samples"]]
    if sorted(row["individuo"] for row in rows) != sorted(expected_names):
        raise PlanExecutionError("execution.output", "Contamination summary does not match the selected sample identities.")
    tables = []
    warnings = []
    for number, row in enumerate(rows, 2):
        count = nonnegative_integer(row["informative_sites"], summary, number, "informative_sites")
        warnings.extend(_numeric_warnings(row, {"mean_contamination"}, summary, number, allow_missing=count == 0))
        warnings.extend(_numeric_warnings(row, {"sd_contamination"}, summary, number, allow_missing=count <= 1))
    for reference, name in zip(step["inputs"]["samples"], expected_names, strict=True):
        path = output_dir / f"contamination_{name}.txt"
        table_artifact = _artifact(path, root, output_dir)
        coordinate_columns = ({"chr", "pos"} if request.get("marker_type", "DNP") == "SNP" else {"chr", "pos1", "pos2"})
        _output_columns(path, coordinate_columns | {"contamination"})
        found = set()
        for number, row in table_rows(path, coordinate_columns | {"contamination"}, "Contamination output"):
            key = locus_key(row, path, number)
            if key in found:
                raise PlanExecutionError("execution.output", f"{path.name}: duplicate locus at row {number}.")
            found.add(key)
            warnings.extend(_numeric_warnings(row, {"contamination"}, path, number, allow_missing=False))
        summary_row = next(row for row in rows if row["individuo"] == name)
        if len(found) != nonnegative_integer(summary_row["informative_sites"], summary, 0, "informative_sites"):
            raise PlanExecutionError("execution.output", f"{path.name}: informative site count differs from its summary.")
        tables.append({"sample": reference["sample"], "source": reference.copy(),
                       "native_name": name, **table_artifact})
    return {"summary": artifact, "contamination-tables": tables, "quality_warnings": warnings}


def _collect_outputs(step: dict, request: dict, root: Path, output_dir: Path) -> dict:
    try:
        result = _collect_outputs_unchecked(step, request, root, output_dir)
        settings = output_dir / "scientific-settings.json"
        artifact = _artifact(settings, root, output_dir)
        document = json.loads(settings.read_text(encoding="utf-8"))
        actual = validate_settings_document(document, step["workflow"])
        if actual != _expected_settings(request):
            raise PlanExecutionError("execution.output", "Scientific settings sidecar differs from the requested parameters.")
        result["scientific-settings"] = artifact
        return result
    except PlanExecutionError:
        raise
    except (ValidationError, UnicodeError, csv.Error, json.JSONDecodeError) as exc:
        raise PlanExecutionError("execution.output", str(exc)) from exc


def validate_standalone_outputs(request: dict) -> dict:
    """Apply plan output contracts to native aliases of a single request."""
    workflow = request["workflow"]
    step = {"id": "analysis", "workflow": workflow}
    if workflow == "dnp-call":
        step["inputs"] = {"samples": [sample["sample_id"] for sample in request["samples"]]}
    elif workflow == "snp-call":
        step["inputs"] = {"sample": "sample_0001"}
    elif workflow == "contamination":
        step["inputs"] = {"samples": [{"sample": Path(sample["name"]).stem}
                                      for sample in request["samples"]]}
    elif workflow == "cpin":
        bindings = []
        marker = request.get("marker_type", "DNP")
        for trio in request["trios"].split(","):
            mother, father, child = [value.strip() for value in trio.split(":")]
            bindings.append({"trio": f"{mother}:{father}:{child}", "mother": {"sample": mother},
                             "father": {"sample": father}, "child": {"sample": child},
                             "native_trio": f"Mother{mother}-Father{father}-Child{child}_{marker}s"})
        step["native_bindings"] = bindings
    else:
        bindings = []
        for pair in request["pairs"].split(","):
            mother, father = [value.strip() for value in pair.split(":")]
            bindings.append({"pair": f"{mother}:{father}", "mother": {"sample": mother},
                             "father": {"sample": father},
                             "native_pair": f"Mother{mother}-Father{father}_{request.get('marker_type', 'DNP')}s"})
        step["native_bindings"] = bindings
    output = Path(request["out_dir"])
    root = output.parent
    return _collect_outputs(step, request, root, output)

