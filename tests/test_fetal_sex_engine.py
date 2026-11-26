"""Both maternal input layouts preserve region identity and upstream count semantics."""

import json
from pathlib import Path
import shutil

import pytest

from nipat_scientific.errors import ValidationError
from nipat_scientific.fetal_sex import prepare_fetal_sex, validate_tables
from nipat_scientific.plan import validate_plan

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
        {"id": roles[role], "kind": kind, "path": request[role]}
        for role, kind in (("dnp", "dnp-table"), ("y", "snp-table"))], "steps": [step]}
    assert validate_plan(plan)["plan"]["steps"] == [step]
    inputs["x"] = roles["dnp"]
    with pytest.raises(ValidationError, match="expected exactly"):
        validate_plan(plan)
    request["x"] = request["dnp"]
    with pytest.raises(ValidationError, match="Invalid fetal-sex"):
        prepare_fetal_sex(request)
