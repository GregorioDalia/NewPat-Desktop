"""Independent analytical checks for the installed downstream models.

The fixtures declare synthetic counts and population frequencies. Expected
answers below follow their documented arithmetic, never candidate output or R.
Only the caller of build_cases executes NIPAT, using its installed backend.
"""

from __future__ import annotations

import csv
from functools import partial
import hashlib
import json
import math
from pathlib import Path
import shutil
from statistics import mean, median


EPSILON = {"SNP": .001, "DNP": .0000892303778101497}
SUMMARY = {"cpi": "Summary_FetalFraction_CPI.csv", "cpin": "Summary_Postnatal_CPI.txt",
           "contamination": "contamination_summary.txt"}
COMMON_PARAMETERS = {
    "other_fraction_max": .1, "homozygous_ref_min": .9, "homozygous_alt_max": .1,
    "heterozygous_min": .4, "heterozygous_max": .6,
    "log_cpi_lower": -4., "log_cpi_upper": 4.,
}
COMMON_CONSTANTS = {
    "ploidy": 2, "allele_alphabet": "ACGT", "missing_result": "NA",
    "heterozygous_transmission": .5, "homozygous_transmission": 1,
    "log_cpi_base": 10, "population_frequencies": "(0, 1]",
    "pi_formula": "paternal transmission (or mismatch constant) / obligatory allele population frequency",
    "other_filter_comparison": "<=",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(actual, expected, label: str) -> None:
    if expected is None:
        require(actual == "NA", f"{label}: expected explicit NA, got {actual!r}")
        return
    try:
        value = float(actual)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: not numeric: {actual!r}") from exc
    require(not isinstance(actual, bool) and math.isfinite(value)
            and math.isclose(value, expected, rel_tol=1e-11, abs_tol=1e-11),
            f"{label}: expected {expected}, got {actual!r}")


def table(path: Path, required: set[str]) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="," if path.suffix == ".csv" else "\t")
        columns = reader.fieldnames or []
        require(required <= set(columns) and len(columns) == len(set(columns)),
                f"Missing or duplicate columns: {path.name}")
        rows = list(reader)
    require(all(None not in row and all(value is not None for value in row.values()) for row in rows),
            f"Incomplete row: {path.name}")
    return rows


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): file_hash(path)
            for path in sorted(root.rglob("*")) if path.is_file()}


FETAL_SEX_EXAMPLES = ("Female_fetus", "Male_fetus")
FETAL_SEX_OUTPUTS = ("Fetal_sex_summary.txt", "Autosomal_informative_sites.txt",
                     "X_informative_sites.txt", "Y_sites.txt")
# Digest of the 14 path/SHA256 pairs from Letizia's two examples at dde1a759.
FETAL_SEX_FIXTURE_DIGEST = "60a792950aa0876cbd1d40ebd0a4574663c574e96f35063f716b90bdab4d7f63"


def fetal_sex_inputs(fixture, sample):
    return [fixture / "inputs" / f"{sample}_{suffix}.txt" for suffix in ("autosomes", "X", "Y")]


def copy_fetal_sex_fixtures(source, destination):
    paths = [path for sample in FETAL_SEX_EXAMPLES for path in fetal_sex_inputs(source, sample)]
    paths.extend(source / "outputs" / sample / name for sample in FETAL_SEX_EXAMPLES for name in FETAL_SEX_OUTPUTS)
    return copy_reference_files(source, destination, paths, FETAL_SEX_FIXTURE_DIGEST)


def copy_reference_files(source, destination, paths, expected_digest):
    hashes = {}
    for path in paths:
        relative = path.relative_to(source)
        require(path.is_file() and path.resolve() == path.absolute(), f"Missing or linked reference table: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[relative.as_posix()] = file_hash(target)
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode("ascii")).hexdigest()
    require(fingerprint == expected_digest, "Reference cases differ from the published examples")
    return hashes


def check_fetal_sex(run, fixture, sample):
    output = run / "output"
    hashes = {}
    for name in FETAL_SEX_OUTPUTS:
        hashes[name] = file_hash(output / name)
        require(hashes[name] == file_hash(fixture / "outputs" / sample / name),
                f"Fetal-sex result differs from the published {sample}/{name}")
    summary, = table(output / "Fetal_sex_summary.txt", {"Sample", "Fetal_sex"})
    return {"sample": summary["Sample"], "fetal_sex": summary["Fetal_sex"], "output_sha256": hashes}


def combined_fetal_dnp(autosomes, x, directory):
    # Retain the autosomal basename so the R summary keeps the reference sample ID.
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / autosomes.name
    with autosomes.open("rb") as auto, x.open("rb") as chromosome_x, path.open("xb") as output:
        header = auto.readline()
        require(header == chromosome_x.readline(), "Reference DNP column headers differ")
        output.write(header)
        shutil.copyfileobj(auto, output)
        shutil.copyfileobj(chromosome_x, output)
    return path


def fetal_sex_cases(fixture, combined_dir=None):
    cases = []
    for sample in FETAL_SEX_EXAMPLES:
        autosomes, x, y = fetal_sex_inputs(fixture, sample)
        case = {"id": "fetal-sex-" + sample.lower().replace("_", "-"), "category": "model", "mode": "auto",
                "validate": partial(check_fetal_sex, fixture=fixture, sample=sample)}
        cases.append({**case, "args": ["fetal-sex", "--autosomes", autosomes, "--x", x, "--y", y]})
        if combined_dir is not None:
            combined = combined_fetal_dnp(autosomes, x, combined_dir)
            cases.append({**case, "id": case["id"] + "-combined",
                          "args": ["fetal-sex", "--dnp", combined, "--y", y]})
    return cases


PRENATAL_FIXTURE_DIGEST = "e8cec0cf076d6c44825447cf3179f2e8ec32a4cc11da9ba68914671053e39608"
PRENATAL_INPUTS = ("MotherA1.txt", "FatherA1.txt", "population_frequencies.txt", "markers.txt")


def prenatal_outputs(marker):
    pair = f"MotherA1-FatherA1_{marker}s"
    return (SUMMARY["cpi"], pair + "_CPI_iterations.csv", pair + "_HOM_child_sites.txt")


def copy_prenatal_fixtures(source, destination):
    paths = [source / section / marker / name
             for marker in ("DNP", "SNP")
             for section, names in (("inputs", PRENATAL_INPUTS), ("outputs", prenatal_outputs(marker)))
             for name in names]
    return copy_reference_files(source, destination, paths, PRENATAL_FIXTURE_DIGEST)


def check_prenatal_example(run, fixture, marker):
    expected_dir = fixture / "outputs" / marker
    observed = {}
    for name in prenatal_outputs(marker):
        reference = expected_dir / name
        with reference.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream, delimiter="," if name.endswith(".csv") else "\t")
            fields, expected_rows = set(reader.fieldnames), list(reader)
        result = run / "output" / name
        actual = table(result, fields)
        require(len(actual) == len(expected_rows), f"Wrong number of rows: {marker}/{name}")
        for index, (row, expected) in enumerate(zip(actual, expected_rows), 1):
            for key, value in expected.items():
                if row[key] == value:
                    continue
                try:
                    wanted = float(value)
                except ValueError as exc:
                    raise ValueError(f"Wrong {marker}/{name} row {index}: {key}") from exc
                number(row[key], wanted, f"{marker}/{name} row {index}: {key}")
        observed[name] = file_hash(result)
    return {"marker": marker, "output_sha256": observed}


def prenatal_example_cases(fixture):
    cases = []
    for marker in ("DNP", "SNP"):
        inputs = fixture / "inputs" / marker
        cases.append({"id": "prenatal-cpi-" + marker.lower(), "category": "model", "mode": "auto",
                      "args": ["cpi", "--input-dir", inputs, "--pairs", "A1:A1", "--popfreq",
                               inputs / "population_frequencies.txt", "--panel", inputs / "markers.txt"],
                      "validate": partial(check_prenatal_example, fixture=fixture, marker=marker)})
    return cases


def settings_expected(workflow, minimum, percent, coverage, include_hom_het, include_zero, *, revised_prenatal=True):
    """Explicit model defaults; observed settings never define the oracle."""
    if workflow == "contamination":
        return ({"other_fraction_max": .1, "homozygous_ref_min": .9,
                 "homozygous_alt_max": .1, "include_zero": include_zero}, {
            "other_fraction_denominator": "N_REF+N_ALT+N_Other",
            "site_contamination": "N_unexpected/(N_REF+N_ALT)",
            "sample_contamination": "arithmetic mean of retained sites",
            "one_site_sd": "NA", "missing_result": "NA"})
    parameters = dict(COMMON_PARAMETERS)
    constants = dict(COMMON_CONSTANTS)
    if workflow == "cpi":
        if revised_prenatal:
            parameters.update(include_homozygous_child=False, min_coverage=None)
        parameters.update(min_fetal_reads=minimum, min_fetal_percent=percent,
                          err_const_snp=EPSILON["SNP"], err_const_dnp=EPSILON["DNP"])
        constants["fetal_fraction_formula"] = "median(2 * fetal_reads/(N_REF+N_ALT))"
    else:
        parameters.update(min_coverage=coverage, include_hom_hom=True, include_hom_het=include_hom_het,
                          include_het_hom=True, include_het_het=True,
                          mismatch_probability_snp=EPSILON["SNP"], mismatch_probability_dnp=EPSILON["DNP"])
        constants["het_het_pi"] = "1 / (f_REF + f_ALT)"
    return parameters, constants


def check_settings(run, workflow, minimum, percent, coverage, include_hom_het, include_zero, *, revised_prenatal=True):
    parameters, constants = settings_expected(workflow, minimum, percent, coverage, include_hom_het, include_zero,
                                              revised_prenatal=revised_prenatal)
    for path in (run / "work/effective-scientific-settings.json", run / "output/scientific-settings.json"):
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        require(record.get("schema_version") == 1 and record.get("workflow") == workflow,
                f"Wrong scientific settings identity: {path.name}")
        observed = record.get("parameters", {})
        require(set(observed) == set(parameters), "Scientific settings are missing or unexpected")
        for name, wanted in parameters.items():
            if type(wanted) in (int, float):
                require(type(observed[name]) in (int, float), f"Wrong settings type: {name}")
                number(observed[name], wanted, f"settings/{name}")
            else:
                require(type(observed[name]) is type(wanted) and observed[name] == wanted,
                        f"Wrong scientific setting: {name}")
        values = record.get("constants", {})
        require(set(values) == set(constants) and all(isinstance(item, dict) and "value" in item
                                                    for item in values.values()),
                "Scientific constants are missing or unexpected")
        for name, wanted in constants.items():
            observed = values[name]["value"]
            if type(wanted) in (int, float):
                require(type(observed) in (int, float), f"Wrong constant type: {name}")
                number(observed, wanted, f"constants/{name}")
            else:
                require(observed == wanted, f"Wrong scientific constant: {name}")


def expected_files(directory: Path, suffix: str, names: set[str]) -> None:
    require({path.name for path in directory.glob(f"*{suffix}")} == names,
            f"Missing, duplicate or unexpected {suffix} files in {directory.name}")


def check_pdfs(output: Path, expected: set[str]) -> None:
    actual = {path.relative_to(output).as_posix() for path in output.rglob("*.pdf")
              if "presentation" not in path.relative_to(output).parts}
    require(actual == expected, "Missing or unexpected analytical PDF")
    for relative in expected:
        data = (output / relative).read_bytes()
        require(len(data) > 64 and data.startswith(b"%PDF-") and b"%%EOF" in data[-1024:],
                f"Empty or incomplete analytical PDF: {relative}")


def check_cpi(output: Path, marker: str, minimum: int | None, families: int, mismatch: bool, percent: float | None) -> int:
    identities = ([f"MotherM-FatherF_{marker}s", f"MotherN-FatherN_{marker}s"] if families == 1 else
                  [f"MotherM{i}-FatherF{i}_{marker}s" for i in range(1, families + 1)])
    fields = {"N_sites_mother", "N_sites_father", "Median_fetal_fraction_raw", "Median_fetal_fraction_percent",
              "Max_logCPI", "Min_logCPI", "Median_logCPI", "Mean_logCPI", "CPI_medianFF",
              "Error_constant", "Min_fetal_reads", "Min_fetal_percent"}
    rows = table(output / SUMMARY["cpi"], fields | {"Pair", "Marker_type"})
    require(len(rows) == len(identities) and {row["Pair"] for row in rows} == set(identities),
            "CPI lost or duplicated an informative/no-sites pair")
    epsilon = EPSILON[marker]
    # Each synthetic maternal locus has 100 REF+ALT reads, so its percentage
    # equals the count. Changing the count and percentage independently changes
    # the reported settings, the retained sites, and/or the first curve threshold.
    contributions = [(1, 5), (2, 5), (3, 4 * epsilon if mismatch else 2), (4, 2)]
    qualified = [(support, pi) for support, pi in contributions
                 if support >= (minimum or 1) and support >= (percent or 0)]
    expected_files(output / "curves", ".tsv", {f"{name}_panel_1.tsv" for name in identities})
    for row in rows:
        identity = row["Pair"]
        require(row["Marker_type"] == marker, "Wrong CPI marker type")
        sites = [] if "MotherN-FatherN" in identity else qualified
        thresholds = list(range(minimum or 1, max((s for s, _ in sites), default=0) + 1))
        logs = []
        curve = table(output / "curves" / f"{identity}_panel_1.tsv",
                      {"Iteration", "InfSites_mother", "InfSites_father", "CPI", "log_CPI", "Mismatch", "NotMismatch"})
        require([int(point["Iteration"]) for point in curve] == thresholds,
                "CPI curve has missing or duplicate thresholds")
        for threshold, point in zip(thresholds, curve):
            retained = [(support, pi) for support, pi in sites if support >= threshold]
            product = math.prod(pi for _, pi in retained)
            logs.append(math.log10(product))
            mismatches = int(mismatch and any(support == 3 for support, _ in retained))
            for name, value in {"InfSites_mother": len(retained), "InfSites_father": len(retained),
                                "CPI": product, "log_CPI": logs[-1], "Mismatch": mismatches,
                                "NotMismatch": len(retained) - mismatches}.items():
                number(point[name], value, f"CPI curve/{identity}/{threshold}/{name}")

        middle = median(support for support, _ in sites) if sites else None
        wanted = {
            "N_sites_mother": len(sites), "N_sites_father": len(sites),
            "Median_fetal_fraction_raw": 2 * middle / 100 if sites else None,
            "Median_fetal_fraction_percent": 2 * middle if sites else None,
            "Max_logCPI": round(max(logs), 3) if logs else None,
            "Min_logCPI": round(min(logs), 3) if logs else None,
            "Median_logCPI": round(median(logs), 3) if logs else None,
            "Mean_logCPI": round(mean(logs), 3) if logs else None,
            "CPI_medianFF": round(logs[thresholds.index(round(middle))], 3) if logs else None,
            "Error_constant": epsilon, "Min_fetal_reads": minimum, "Min_fetal_percent": percent,
        }
        for name, value in wanted.items():
            number(row[name], value, f"CPI/{identity}/{name}")
    check_pdfs(output, {"plots/All_CPIplots.pdf", *(f"plots/{name}_CPIplot.pdf" for name in identities)})
    return len(rows)


def check_cpin(output: Path, marker: str, coverage: int | None, families: int, include_hom_het: bool) -> int:
    identities = ([f"MotherM-FatherF-ChildC_{marker}s"] if families == 1 else
                  [f"MotherM{i}-FatherF{i}-ChildC{i}_{marker}s" for i in range(1, families + 1)])
    fields = {"N_sites", "N_hom_hom", "N_hom_het", "N_het_hom", "N_het_het", "Matching_sites",
              "Mismatching_sites", "No_obligatory_allele_sites", "Maternal_incompatible_sites",
              "CPI", "Log10_CPI", "Mismatch_probability", "Min_coverage",
              "Include_hom_hom", "Include_hom_het", "Include_het_hom", "Include_het_het"}
    rows = table(output / SUMMARY["cpin"], fields | {"Trio", "Marker_type"})
    require(len(rows) == families and {row["Trio"] for row in rows} == set(identities),
            "Postnatal CPI lost or duplicated a trio")
    expected_files(output, "_sites.txt", {f"{name}_sites.txt" for name in identities})
    require(not list((output / "curves").glob("*.tsv")), "Unexpected postnatal threshold curve")
    check_pdfs(output, set())

    # Each entry records the predetermined result of the nine synthetic genotypes.
    # The minimum depth across all three roles is the child's depth for these inputs.
    epsilon = EPSILON[marker]
    loci = [
        (10, "eligible", "hom_het", "ALT", .5, 1.25, "match"),
        (10, "eligible", "hom_het", "ALT", 0, epsilon / .4, "mismatch"),
        (10, "eligible", "hom_hom", "REF", 1, 1 / .6, "match"),
        (10, "mother_child_incompatible", "NA", "NA", None, None, "NA"),
        (10, "eligible", "het_het", "NA", None, 1, "no_obligatory_allele"),
        (2, "eligible", "hom_het", "ALT", 0, epsilon / .4, "mismatch"),
        (0, "quality_filter", "NA", "NA", None, None, "NA"),
        (30, "quality_filter", "NA", "NA", None, None, "NA"),
        (10, "father_unassigned", "hom_het", "ALT", None, None, "NA"),
    ]
    position = "pos" if marker == "SNP" else "pos1"
    for row in rows:
        identity = row["Trio"]
        require(row["Marker_type"] == marker, "Wrong postnatal CPI marker type")
        sites = table(output / f"{identity}_sites.txt", {"chr", position, "Status", "Paternity_Index",
                      "Mismatch", "Paternal_transmission", "Required_paternal_allele", "Genotype_combination",
                      "Paternity_status"})
        require(len(sites) == len(loci) and {int(site[position]) for site in sites} == set(range(100, 1000, 100)),
                "Postnatal CPI sites are missing or duplicated")
        included = []
        incompatible = 0
        for site in sites:
            pos = int(site[position])
            depth, status, family, allele, transmission, pi, outcome = loci[pos // 100 - 1]
            if coverage is not None and depth < coverage:
                status, family, allele = "quality_filter", "NA", "NA"
            elif status == "eligible" and family == "hom_het" and not include_hom_het:
                status = "combination_not_selected"
            if status == "eligible":
                included.append((family, outcome, pi))
            else:
                pi = transmission = None
                outcome = "NA"
            incompatible += status == "mother_child_incompatible"
            expected = {"chr": "chr1", "Status": status, "Genotype_combination": family,
                        "Required_paternal_allele": allele, "Paternity_status": outcome,
                        "Mismatch": {"match": "FALSE", "mismatch": "TRUE"}.get(outcome, "NA")}
            for key, value in expected.items():
                require(site[key] == value, f"Postnatal CPI/{identity}/{pos}/{key}: expected {value}, got {site[key]}")
            number(site["Paternity_Index"], pi, f"Postnatal CPI site/{pos}/PI")
            number(site["Paternal_transmission"], transmission, f"Postnatal CPI site/{pos}/transmission")
            if marker == "DNP":
                number(site["pos2"], pos + 1, "Postnatal CPI second coordinate")

        cpi = math.prod(pi for _, _, pi in included) if included else None
        wanted = {"N_sites": len(included), "Maternal_incompatible_sites": incompatible,
                  "Matching_sites": sum(outcome == "match" for _, outcome, _ in included),
                  "Mismatching_sites": sum(outcome == "mismatch" for _, outcome, _ in included),
                  "No_obligatory_allele_sites": sum(outcome == "no_obligatory_allele" for _, outcome, _ in included),
                  "CPI": cpi, "Log10_CPI": math.log10(cpi) if included else None,
                  "Mismatch_probability": epsilon, "Min_coverage": coverage}
        for combination in ("hom_hom", "hom_het", "het_hom", "het_het"):
            wanted["N_" + combination] = sum(family == combination for family, _, _ in included)
            enabled = combination != "hom_het" or include_hom_het
            require(row["Include_" + combination] == ("TRUE" if enabled else "FALSE"),
                    f"Postnatal CPI selection differs for {combination}")
        for name, value in wanted.items():
            number(row[name], value, f"Postnatal CPI/{identity}/{name}")
    return len(rows)


def check_contamination(output: Path, marker: str, include_zero: bool, families: int) -> int:
    identities = {f"Sample{i}" for i in range(1, families + 1)}
    rows = table(output / SUMMARY["contamination"], {"individuo", "informative_sites", "mean_contamination", "sd_contamination"})
    require(len(rows) == families and {row["individuo"] for row in rows} == identities,
            "Contamination lost or duplicated a sample")
    for row in rows:
        for name, value in {"informative_sites": 2 if include_zero else 1,
                            "mean_contamination": .025 if include_zero else .05,
                            "sd_contamination": math.sqrt(.00125) if include_zero else None}.items():
            number(row[name], value, f"Contamination/{row['individuo']}/{name}")
    expected_files(output, ".txt", {SUMMARY["contamination"], *(f"contamination_{name}.txt" for name in identities)})
    position = "pos" if marker == "SNP" else "pos1"
    for identity in identities:
        sites = table(output / f"contamination_{identity}.txt",
                      {"chr", position, "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count",
                       "ratio_REF_ALT", "ratio_Other", "N_unexpected", "contamination"})
        wanted_positions = {100, 200} if include_zero else {100}
        require(len(sites) == len(wanted_positions) and {int(row[position]) for row in sites} == wanted_positions,
                "Contamination retained the wrong sites")
        for row in sites:
            first = int(row[position]) == 100
            require(row["chr"] == "chr1" and row["REF"] == ("A" if marker == "SNP" else "AA")
                    and row["ALT"] == ("C" if marker == "SNP" else "CC"), "Wrong contamination locus/alleles")
            if marker == "DNP":
                number(row["pos2"], int(row[position]) + 1, "Contamination second coordinate")
            for name, value in {"N_REF": 95 if first else 100, "N_ALT": 5 if first else 0,
                                "N_Other": 11 if first else 0, "total_count": 111 if first else 100,
                                "ratio_REF_ALT": .95 if first else 1, "ratio_Other": 11 / 111 if first else 0,
                                "N_unexpected": 5 if first else 0, "contamination": .05 if first else 0}.items():
                number(row[name], value, f"Contamination site/{identity}/{row[position]}/{name}")
    return len(rows)


def validate_model(run: Path, *, workflow: str, marker: str, families: int = 1,
                   minimum: int | None = 2, percent: float | None = None, coverage: int | None = None,
                   include_hom_het: bool = True, include_zero: bool = True, mismatch: bool = False,
                   revised_prenatal: bool = True) -> dict:
    output = run / "output"
    check_settings(run, workflow, minimum, percent, coverage, include_hom_het, include_zero,
                   revised_prenatal=revised_prenatal)
    if workflow == "cpi":
        count = check_cpi(output, marker, minimum, families, mismatch, percent)
    elif workflow == "cpin":
        count = check_cpin(output, marker, coverage, families, include_hom_het)
    else:
        count = check_contamination(output, marker, include_zero, families)
    scientific = {path.relative_to(output).as_posix(): file_hash(path)
                  for path in sorted(output.rglob("*"))
                  if path.is_file() and path.suffix in {".txt", ".tsv", ".csv"}
                  and "presentation" not in path.relative_to(output).parts and path.name != "resources.tsv"}
    return {"workflow": workflow, "marker": marker, "families": families,
            "summary_rows": count, "scientific_sha256": scientific}


def validate_case(run: Path, *, inputs: Path, original: dict, **options) -> dict:
    require(tree_hashes(inputs) == original, "The installed analysis modified an original test input")
    return validate_model(run, **options)


def build_cases(fixtures: Path, generated: Path, *, revised_prenatal=True) -> list[dict]:
    """Create analytical and batch cases plus precise input rejections."""
    cases = []
    generated.mkdir(parents=True, exist_ok=True)

    def add(marker, workflow, variant, *, mode="serial", families=1, minimum=2,
            percent=None, coverage=None, include_hom_het=True,
            include_zero=True, metadata=False, mismatch=False):
        identity = f"models-{marker.lower()}-{workflow}-{variant}"
        inputs = generated / identity
        shutil.copytree(fixtures / "five_modules" / marker / workflow, inputs)
        if families > 1 and workflow in {"cpi", "cpin"}:
            for index in range(1, families + 1):
                roles = (("Mother", "M"), ("Father", "F"), ("Child", "C")) if workflow == "cpin" else (("Mother", "M"), ("Father", "F"))
                for role, name in roles:
                    shutil.copyfile(inputs / f"{role}{name}.txt", inputs / f"{role}{name}{index}.txt")
        if metadata:
            path = inputs / "population.tsv"
            lines = path.read_text(encoding="utf-8").splitlines()
            path.write_text(lines[0] + "\tunused_metadata\n" + "".join(line + "\tNA\n" for line in lines[1:]), encoding="utf-8")
        if mismatch:
            path = inputs / "FatherF.txt"
            rows = table(path, {"N_REF", "N_ALT"})
            rows[1].update(N_REF="100", N_ALT="0")
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        if workflow == "contamination":
            calls = inputs / "calls"
            calls.mkdir()
            for index in range(1, families + 1):
                shutil.copyfile(inputs / "Calls.txt", calls / f"Sample{index}.txt")
            args = ["--set", f"contamination.include_zero={str(include_zero).lower()}",
                    workflow, "--input-dir", calls, "--panel", inputs / "panel.tsv"]
        else:
            options = {"min_fetal_reads": minimum, "min_fetal_percent": percent} if workflow == "cpi" else {
                "min_coverage": coverage, "include_hom_het": "false" if not include_hom_het else None}
            flags = [value for name, setting in options.items() if setting is not None
                     for value in ("--set", f"{workflow}.{name}={setting}")]
            selected = ("M:F:C" if workflow == "cpin" else "M:F,N:N") if families == 1 else ",".join(
                f"M{i}:F{i}:C{i}" if workflow == "cpin" else f"M{i}:F{i}" for i in range(1, families + 1))
            args = [*flags, workflow, "--input-dir", inputs,
                    "--trios" if workflow == "cpin" else "--pairs", selected,
                    "--popfreq", inputs / "population.tsv"]
        cases.append({"id": identity, "category": "downstream-analytical" if families == 1 else "downstream-batch",
                      "args": args, "mode": mode,
                      "validate": partial(validate_case, inputs=inputs, original=tree_hashes(inputs),
                                          workflow=workflow, marker=marker, families=families,
                                          minimum=minimum, percent=percent, coverage=coverage, include_hom_het=include_hom_het,
                                          include_zero=include_zero, mismatch=mismatch, revised_prenatal=revised_prenatal),
                      **({"compare_group": f"models-{marker.lower()}-{workflow}-batch3"} if families > 1 else {})})

    for marker in ("SNP", "DNP"):
        add(marker, "cpin", "default")
        add(marker, "cpin", "coverage10", coverage=10)
        add(marker, "cpin", "coverage101", coverage=101)
        add(marker, "cpin", "exclude-hom-het", include_hom_het=False)
        for name, options in (("default", {}), ("minimum1", {"minimum": 1}),
                              ("percent-only", {"minimum": None, "percent": 2.5}),
                              ("count-and-percent", {"minimum": 2, "percent": 3}),
                              ("no-sites", {"minimum": 5}), ("metadata-na", {"metadata": True}),
                              ("mismatch", {"mismatch": True})):
            add(marker, "cpi", name, **options)
        add(marker, "contamination", "include-zero")
        add(marker, "contamination", "exclude-zero", include_zero=False)
        for workflow in ("cpin", "cpi", "contamination"):
            for mode in ("serial", "auto", "cap2"):
                add(marker, workflow, f"batch3-{mode}", families=3, mode=mode)
    for workflow, variant, expected in (
        ("contamination", "negative-count", r"N_REF.*intero non negativo"),
        ("cpi", "zero-frequency", r"Ref_f\.pop.*finita tra 0 e 1"),
        ("cpin", "duplicate-trio", r"Terna (?:CPI postnatale|CPIN) duplicata\."),
    ):
        identity = f"models-invalid-{workflow}-{variant}"
        inputs = generated / identity
        shutil.copytree(fixtures / "five_modules/SNP" / workflow, inputs)
        if workflow != "cpin":
            path = inputs / ("Calls.txt" if workflow == "contamination" else "population.tsv")
            column = "N_REF" if workflow == "contamination" else "Ref_f.pop"
            rows = table(path, {column})
            rows[0][column] = "-1" if workflow == "contamination" else "0"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
        if workflow == "contamination":
            args = [workflow, "--input", inputs / "Calls.txt", "--panel", inputs / "panel.tsv"]
        else:
            args = [workflow, "--input-dir", inputs, "--pairs" if workflow == "cpi" else "--trios",
                    "M:F" if workflow == "cpi" else "M:F:C,M:F:C", "--popfreq", inputs / "population.tsv"]
        cases.append({"id": identity, "category": "invalid-input", "args": args,
                      "mode": "serial", "validate": None, "expect_failure": expected})
    return cases
