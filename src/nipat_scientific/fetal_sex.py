"""Adapt three explicitly assigned maternal cfDNA calling tables to the upstream R CLI."""

from __future__ import annotations

import math
from pathlib import Path
import re
import shutil

from nipat_scientific.errors import ValidationError
from nipat_scientific.files import nonnegative_integer, require_file, table_rows, write_input_report
from nipat_scientific.settings import normalize_settings

ROLES = ("autosomes", "x", "y")
NATIVE_FLAGS = {
    "max_other_fraction": "max_other_fraction", "maternal_hom_threshold": "maternal_hom_threshold",
    "include_zero_coverage_y": "include_zero_coverage_Y", "min_fetal_reads": "min_fetal_reads",
    "min_fetal_percent": "min_fetal_percent", "a_threshold": "A_threshold",
    "b_female_max": "B_female_max", "b_male_min": "B_male_min",
    "c_female_max": "C_female_max", "c_male_min": "C_male_min",
}
SUMMARY = "Fetal_sex_summary.txt"
SITE_TABLES = {"autosomes": "Autosomal_informative_sites.txt", "x": "X_informative_sites.txt", "y": "Y_sites.txt"}
COUNTS = ("N_REF", "N_ALT", "N_Other", "total_count")
AUTOSOMES = frozenset(str(n) for n in range(1, 23))


def _marker_columns(role):
    return ("chr", "pos", "REF", "ALT") if role == "y" else ("chr", "pos1", "pos2", "REF", "ALT")


def validate_inputs(autosomes: Path, x: Path, y: Path) -> None:
    for role, path in zip(ROLES, (autosomes, x, y), strict=True):
        path = require_file(path, f"Maternal cfDNA {role}")
        markers = _marker_columns(role)
        seen = set()
        for number, row in table_rows(path, set(markers) | set(COUNTS), f"Maternal cfDNA {role}"):
            key = tuple(row[col] for col in markers)
            if any(v in {"", "NA"} for v in key) or key in seen:
                raise ValidationError(f"{path.name}: missing or duplicate marker on line {number}.")
            seen.add(key)
            chromosome = re.sub("^chr", "", row["chr"], flags=re.IGNORECASE)
            if chromosome not in (AUTOSOMES if role == "autosomes" else {role.upper()}):
                raise ValidationError(f"{path.name}: chromosome on line {number} does not belong to {role}.")
            ref, alt, other, total = (nonnegative_integer(row[col], path, number, col) for col in COUNTS)
            if total < ref + alt + other:
                raise ValidationError(f"{path.name}: total_count is too small on line {number}.")
        if not seen:
            raise ValidationError(f"{path.name}: empty {role} calling table.")


def prepare_fetal_sex(request: dict) -> list[str]:
    from nipat_scientific.presentation import validate_request_presentation

    fields = {"schema_version", "workflow", *ROLES, "work_dir", "out_dir"}
    if (not isinstance(request, dict) or not fields.issubset(request)
            or set(request) - fields - {"scientific_settings", "presentation"}
            or type(request["schema_version"]) is not int or request["schema_version"] != 1
            or request["workflow"] != "fetal-sex"):
        raise ValidationError("Invalid fetal-sex v1 request.")
    validate_request_presentation(request)
    paths = {}
    for key in (*ROLES, "work_dir", "out_dir"):
        raw = request[key]
        if not isinstance(raw, str) or not Path(raw).is_absolute() or '\x00' in raw:
            raise ValidationError(f"{key}: expected an absolute path.")
        paths[key] = Path(raw)
    work, out = paths["work_dir"], paths["out_dir"]
    sources = [paths[key] for key in ROLES]
    if (work.is_symlink() or out.is_symlink() or work.resolve().is_relative_to(out.resolve())
            or out.resolve().is_relative_to(work.resolve())
            or any(s.resolve().is_relative_to(d.resolve()) for s in sources for d in (work, out))):
        raise ValidationError("Fetal-sex inputs and working/output directories must be separate.")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValidationError("Fetal-sex output directory must be new or empty.")
    values = normalize_settings("fetal-sex", request.get("scientific_settings"))
    validate_inputs(*sources)
    work.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    write_input_report(work, "fetal-sex", [])
    # The unmodified script requires a new destination even when the client has already created out.
    argv = ["--autosomes", str(sources[0]), "--X", str(sources[1]), "--Y", str(sources[2]),
            "--out", str(out / ".native-fetal-sex")]
    for key, flag in NATIVE_FLAGS.items():
        value = values[key]
        if value is not None:
            argv.extend(["--" + flag, str(value).upper() if isinstance(value, bool) else str(value)])
    return argv


def validate_tables(request: dict, directory: Path) -> None:
    values = normalize_settings("fetal-sex", request.get("scientific_settings"))
    path = directory / SUMMARY
    settings_columns = {key: flag[:1].upper() + flag[1:] for key, flag in NATIVE_FLAGS.items()}
    columns = {"Sample", "Fetal_sex", "N_A_original", "N_A_sites", "N_X_original", "N_X_sites",
               "N_Y_sites", "N_Y_covered_sites", "N_Y_sites_used", "Fetal_reads_A", "Fetal_reads_X",
               "Reads_Y", "MFF_A", "MFF_X", "MFF_Y", "Ratio_A", "Ratio_B", "Ratio_C",
               *settings_columns.values()}
    rows = list(table_rows(path, columns, "Fetal-sex summary"))
    if len(rows) != 1:
        raise ValidationError("Expected one fetal-sex summary row per maternal cfDNA sample.")
    number, row = rows[0]
    sample = Path(request["autosomes"]).stem.removeprefix("full_output_")
    if row["Sample"] != sample or row["Fetal_sex"] not in {"F", "M", "Undetermined"}:
        raise ValidationError("Fetal-sex sample identity or classification is invalid.")
    for key, col in settings_columns.items():
        expected = values[key]
        raw = row[col]
        if expected is None:
            valid = raw == "NA"
        elif isinstance(expected, bool):
            valid = raw == str(expected).upper()
        else:
            try:
                valid = math.isclose(float(raw), expected, rel_tol=1e-12)
            except ValueError:
                valid = False
        if not valid:
            raise ValidationError(f"Fetal-sex summary differs from the requested {col}.")
    for col in ("MFF_A", "MFF_X", "MFF_Y", "Ratio_A", "Ratio_B", "Ratio_C"):
        if row[col] == "NA":
            if col == "MFF_Y" or row["Fetal_sex"] != "Undetermined":
                raise ValidationError(f"Unexpected missing value in fetal-sex summary: {col}.")
            continue
        try:
            value = float(row[col])
        except ValueError as exc:
            raise ValidationError(f"Invalid fetal-sex estimate: {col}.") from exc
        if not value >= 0 or not math.isfinite(value) and not (col.startswith("Ratio_") and row[col] == "Inf"):
            raise ValidationError(f"Invalid fetal-sex estimate: {col}.")
    for role, count_col in zip(ROLES, ("N_A_sites", "N_X_sites", "N_Y_sites"), strict=True):
        count = nonnegative_integer(row[count_col], path, number, count_col)
        extra = {"Y_reads", "Covered", "Included"} if role == "y" else {
            "ratio_Ref_mother", "ratio_Other", "fetal_reads", "fetal_percent"}
        audit = directory / SITE_TABLES[role]
        actual = sum(1 for _ in table_rows(audit, set(_marker_columns(role)) | set(COUNTS) | extra, role))
        if count != actual:
            raise ValidationError(f"Fetal-sex summary differs from the {role} site table.")


def publish_outputs(request: dict) -> None:
    """Expose the four native output files after a successful process and contract check."""
    out = Path(request["out_dir"])
    native = out / ".native-fetal-sex"
    names = (SUMMARY, *SITE_TABLES.values())
    if (native.is_symlink() or not native.is_dir()
            or {p.name for p in native.iterdir()} != set(names)
            or any((native / n).is_symlink() or not (native / n).is_file() for n in names)):
        raise ValidationError("Incomplete fetal-sex output directory.")
    for name in names:
        if (out / name).exists() or (out / name).is_symlink():
            raise ValidationError(f"Fetal-sex destination already exists: {name}")
    with (Path(request["work_dir"]) / "effective-scientific-settings.json").open("rb") as src:
        with (out / "scientific-settings.json").open("xb") as dst:
            shutil.copyfileobj(src, dst)
    for name in names:
        (native / name).rename(out / name)
    native.rmdir()
