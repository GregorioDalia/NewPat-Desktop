"""Both maternal input layouts preserve region identity and upstream count semantics."""

import json
from pathlib import Path
import shutil

import pytest

from newpat_scientific.errors import ValidationError
from newpat_scientific.fetal_sex import prepare_fetal_sex, validate_tables
from newpat_scientific.plan import validate_plan

FIXTURE = Path(__file__).parent / "fixtures/fetal_sex"
ROLES = {"autosomes": "autosomes", "x": "X", "y": "Y"}


def request_at(root):
    return {"schema_version": 1, "workflow": "fetal-sex",
            **{role: str(FIXTURE / "inputs" / f"Female_fetus_{suffix}.txt") for role, suffix in ROLES.items()},
            "work_dir": str(root / "work"), "out_dir": str(root / "output")}


def test_fetal_sex_plan_requires_two_dnp_tables_and_one_snp_table():
    plan = {"schema_version": 1, "samples": [
        {"id": key, "kind": "snp-table" if key == "y" else "dnp-table", "path": f"/workspace/inputs/{key}.txt"}
        for key in ROLES], "steps": [{"id": "classification", "workflow": "fetal-sex",
                                     "inputs": {key: key for key in ROLES}, "parameters": {}}]}
    result = validate_plan(plan)
    assert result["plan"]["steps"] == plan["steps"]
    plan["steps"][0]["inputs"]["y"] = "autosomes"
    with pytest.raises(ValidationError, match="expected snp-table, got dnp-table"):
        validate_plan(plan)


def test_fetal_sex_rejects_swapped_x_and_autosomes_before_staging(tmp_path):
    request = request_at(tmp_path)
    request["autosomes"], request["x"] = request["x"], request["autosomes"]
    with pytest.raises(ValidationError, match="does not belong"):
        prepare_fetal_sex(request)
    assert not (tmp_path / "work").exists()


def test_fetal_sex_accepts_upstream_total_above_read_sum_and_percent_only(tmp_path):
    request = request_at(tmp_path)
    table = tmp_path / "autosomes.txt"
    table.write_text("chr\tpos1\tpos2\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
                     "chr1\t100\t101\tAC\tGT\t90\t1\t2\t100\n")
    request["autosomes"] = str(table)
    request["scientific_settings"] = {"min_fetal_percent": 1}
    argv = prepare_fetal_sex(request)
    assert "--min_fetal_percent" in argv and "--min_fetal_reads" not in argv
    assert not Path(argv[argv.index("--out") + 1]).exists()


def test_fetal_sex_validates_sample_settings_and_site_counts(tmp_path):
    request = request_at(tmp_path)
    out = tmp_path / "output"
    shutil.copytree(FIXTURE / "outputs/Female_fetus", out)
    validate_tables(request, out)
    request["scientific_settings"] = {"a_threshold": 0.6}
    with pytest.raises(ValidationError, match="A_threshold"):
        validate_tables(request, out)
    request.pop("scientific_settings")
    audit = out / "Autosomal_informative_sites.txt"
    rows = audit.read_text().splitlines()
    audit.write_text("\n".join(rows[:-1]) + "\n")
    with pytest.raises(ValidationError, match="autosomes site table"):
        validate_tables(request, out)

def combined_request(root):
    request = request_at(root)
    autosomes = Path(request.pop("autosomes"))
    x = Path(request.pop("x"))
    header, *a_rows = autosomes.read_text().splitlines()
    _, *x_rows = x.read_text().splitlines()
    mixed = root / autosomes.name
    mixed.write_text("\n".join([header, a_rows[0], *x_rows, *a_rows[1:]]) + "\n")
    return dict(request, dnp=str(mixed))


def test_combined_regions_stage_without_altering_input_or_sample_identity(tmp_path):
    request = combined_request(tmp_path)
    request["presentation"] = {"samples": {"dnp": "Maternal DNP", "y": "Maternal Y"}, "pairs": {}}
    dnp = Path(request["dnp"])
    before = dnp.read_bytes()
    argv = prepare_fetal_sex(request)
    autosomes = Path(argv[argv.index("--autosomes") + 1])
    x = Path(argv[argv.index("--X") + 1])
    assert autosomes.name == dnp.name
    assert autosomes.read_text() == (FIXTURE / "inputs" / dnp.name).read_text()
    assert x.read_text() == (FIXTURE / "inputs/Female_fetus_X.txt").read_text()
    assert argv[argv.index("--Y") + 1] == request["y"]
    assert dnp.read_bytes() == before
    report = json.loads((Path(request["work_dir"]) / "input-validation.json").read_text())
    assert [(item["source"], item["prepared"]) for item in report["normalizations"]] == [
        (str(dnp), str(autosomes)), (str(dnp), str(x))]
    validate_tables(request, FIXTURE / "outputs/Female_fetus")


@pytest.mark.parametrize("change,error", [
    ("no-x", "missing x"), ("no-autosomes", "missing autosomes"),
    ("unknown", "does not belong"), ("duplicate", "duplicate marker"), ("bad-count", "total_count"),
])
def test_combined_rejects_invalid_or_missing_region_and_discards_partial_tables(tmp_path, change, error):
    request = combined_request(tmp_path)
    dnp = Path(request["dnp"])
    header, *rows = dnp.read_text().splitlines()
    if change == "no-x":
        rows = [row for row in rows if not row.startswith("chrX")]
    elif change == "no-autosomes":
        rows = [row for row in rows if row.startswith("chrX")]
    elif change == "unknown":
        rows.append(rows[-1].replace("chr1", "chrY", 1))
    elif change == "duplicate":
        rows.append(rows[-1].removeprefix("chr"))
    else:
        rows.append("chrX\t21\t22\tAG\tTT\t9\t1\t0\t2")
    dnp.write_text("\n".join([header, *rows]) + "\n")
    with pytest.raises(ValidationError, match=error):
        prepare_fetal_sex(request)
    assert not (tmp_path / "work/regional-dnp").exists()
    assert not (tmp_path / "output").exists()


def test_combined_plan_accepts_only_the_explicit_two_table_layout(tmp_path):
    request = combined_request(tmp_path)
    roles = {"dnp": "maternal_dnp", "y": "maternal_y"}
    inputs = {"dnp": roles["dnp"], "y": roles["y"]}
    step = {"id": "sex", "workflow": "fetal-sex", "inputs": inputs, "parameters": {}}
    plan = {"schema_version": 1, "samples": [
        {"id": roles[role], "kind": kind, "path": f"/workspace/inputs/{role}.txt"}
        for role, kind in (("dnp", "dnp-table"), ("y", "snp-table"))], "steps": [step]}
    assert validate_plan(plan)["plan"]["steps"] == [step]
    inputs["x"] = roles["dnp"]
    with pytest.raises(ValidationError, match="expected exactly"):
        validate_plan(plan)
    request["x"] = request["dnp"]
    with pytest.raises(ValidationError, match="Invalid fetal-sex"):
        prepare_fetal_sex(request)


def test_generated_tables_are_ordered_by_producers_and_bound_to_one_bam():
    from newpat_scientific.presentation import step_presentation
    from newpat_scientific.progress import step_sample_ids

    mother = "Maternal"
    inputs = {"dnp": {"step": "dnpcall", "output": "dnp-tables", "sample": mother},
              "y": {"step": "snpcall", "output": "snp-tables", "sample": mother}}
    sex = {"id": "classify", "workflow": "fetal-sex", "inputs": inputs, "parameters": {}}
    callers = [{"id": "dnpcall", "workflow": "dnp-call", "parameters": {"parallel": True},
                "inputs": {"samples": [mother], "panel": "/dnp", "reference": "/fa"}},
               {"id": "snpcall", "workflow": "snp-call", "parameters": {"mode": "bam"},
                "inputs": {"sample": mother, "panel": "/snp", "reference": "/fa"}}]
    plan = {"schema_version": 1, "samples": [{"id": mother, "kind": "bam", "path": "/mother.bam"}],
            "steps": [sex, *callers], "presentation": {"samples": {mother: "Mother.bam"}, "pairs": {}}}
    checked = validate_plan(plan)
    assert checked["execution_order"] == ["dnpcall", "snpcall", "classify"]
    assert checked == validate_plan(checked["plan"])
    assert step_sample_ids(sex) == [mother]
    assert step_presentation(plan, sex, {})["samples"] == dict.fromkeys(ROLES, "Mother.bam")
    inputs["y"] = dict(inputs["y"], sample="Other")
    with pytest.raises(ValidationError, match="same maternal BAM"):
        validate_plan(plan)
    inputs["y"] = dict(inputs["dnp"])
    with pytest.raises(ValidationError, match="snp-tables"):
        validate_plan(plan)
    inputs["y"] = dict(inputs["dnp"], output="snp-tables")
    with pytest.raises(ValidationError, match="does not produce snp-tables"):
        validate_plan(plan)


def test_generated_tables_project_only_required_regions_and_audit_uncovered_loci(tmp_path):
    from newpat_scientific.fetal_sex import stage_calling_tables

    inputs = combined_request(tmp_path)
    dnp = Path(inputs["dnp"])
    with dnp.open("a") as stream:
        stream.write("chrX\t11\t12\tGA\tTT\t0\t0\t0\tNA\nchrY\t11\t12\tGA\tTT\t7\t0\t0\t7\n")
    original_y = Path(inputs["y"]).read_text()
    snp = tmp_path / "snp.txt"
    snp.write_text(original_y + "chrX\t21\tG\tT\t1\t0\t0\t1\n")
    source_rows = dnp.read_bytes(), snp.read_bytes()
    targets, warnings, normalized = stage_calling_tables({"dnp": dnp, "y": snp}, tmp_path / "stage", sample="Maternal")
    assert targets["autosomes"].name == "full_output_Maternal.txt"
    assert targets["autosomes"].read_text() == (FIXTURE / "inputs/Female_fetus_autosomes.txt").read_text()
    assert targets["x"].read_text() == (FIXTURE / "inputs/Female_fetus_X.txt").read_text() + "chrX\t11\t12\tGA\tTT\t0\t0\t0\t0\n"
    assert targets["y"].read_text() == original_y
    assert len(warnings) == 1 and warnings[0]["count"] == 1
    assert warnings[0]["code"] == "fetal_sex.no_retained_reads"
    request = dict(request_at(tmp_path), **{role: str(file) for role, file in targets.items()})
    prepare_fetal_sex(request, caller_warnings=warnings, caller_normalizations=normalized)
    audit = json.loads((tmp_path / "work/input-validation.json").read_text())
    assert audit["warnings"] == warnings
    assert {(row["source"], row["prepared"]) for row in audit["normalizations"]} == {
        (str(dnp), str(targets["autosomes"])), (str(dnp), str(targets["x"])), (str(snp), str(targets["y"]))}
    assert (dnp.read_bytes(), snp.read_bytes()) == source_rows
    inputs["y"] = str(snp)
    with pytest.raises(ValidationError, match="does not belong to y"):
        prepare_fetal_sex(inputs)


def test_generated_tables_require_y_markers_and_reject_missing_counts_with_reads(tmp_path):
    from newpat_scientific.fetal_sex import stage_calling_tables

    inputs = combined_request(tmp_path)
    dnp = Path(inputs["dnp"])
    snp = tmp_path / "snp.txt"
    snp.write_text(Path(inputs["y"]).read_text().replace("chrY", "chr1"))
    stage = tmp_path / "regions"
    with pytest.raises(ValidationError, match="no y markers"):
        stage_calling_tables({"dnp": dnp, "y": snp}, stage, sample="Maternal")
    assert not stage.exists()
    with dnp.open("a") as stream:
        stream.write("chrX\t31\t32\tGA\tTT\t1\t0\t0\tNA\n")
    with pytest.raises(ValidationError, match="total_count"):
        stage_calling_tables({"dnp": dnp, "y": Path(inputs["y"])}, stage, sample="Maternal")
    assert not stage.exists()


def test_registered_split_tables_normalize_only_zero_dnp_rows_and_keep_region_assignments(tmp_path):
    from newpat_scientific.fetal_sex import stage_calling_tables, validate_inputs

    tables = {}
    for role in ROLES:
        src = Path(request_at(tmp_path)[role])
        tables[role] = tmp_path / src.name
        shutil.copyfile(src, tables[role])
    for role, chromosome in (("autosomes", "chr2"), ("x", "chrX")):
        with tables[role].open("a") as stream:
            stream.write(f"{chromosome}\t11\t12\tGA\tTT\t0\t0\t0\tNA\n")
    with tables["y"].open("a") as stream:
        stream.write("chr2\t14\tG\tT\t8\t4\t0\t12\n")
    validate_inputs(**tables, project_regions=True)
    targets, warnings, _ = stage_calling_tables(tables, tmp_path / "stage")
    for role in ("autosomes", "x"):
        assert targets[role].read_text().endswith("0\t0\t0\t0\n")
        assert tables[role].read_text().endswith("0\t0\t0\tNA\n")
    assert "chr2" not in targets["y"].read_text()
    assert {w["path"] for w in warnings} == {str(tables["autosomes"]), str(tables["x"])}
    with pytest.raises(ValidationError, match="does not belong to autosomes"):
        validate_inputs(autosomes=tables["x"], x=tables["autosomes"], y=tables["y"], project_regions=True)
    with tables["x"].open("a") as stream:
        stream.write("chrX\t21\t22\tGA\tTT\t1\t0\t0\tNA\n")
    with pytest.raises(ValidationError, match="total_count"):
        stage_calling_tables(tables, tmp_path / "invalid-stage")
    assert not (tmp_path / "invalid-stage").exists()
