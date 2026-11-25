"""The three region files are explicitly typed and preserve upstream count semantics."""

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


def test_fetal_sex_plan_requires_two_dnp_tables_and_one_snp_table(tmp_path):
    request = request_at(tmp_path)
    plan = {"schema_version": 1, "samples": [
        {"id": key, "kind": "snp-table" if key == "y" else "dnp-table", "path": request[key]}
        for key in ROLES], "steps": [{"id": "classification", "workflow": "fetal-sex",
                                     "inputs": {key: key for key in ROLES}, "parameters": {}}]}
    result = validate_plan(plan)
    assert result["plan"]["steps"] == plan["steps"]
    plan["steps"][0]["inputs"]["y"] = "autosomes"
    with pytest.raises(ValidationError):
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
