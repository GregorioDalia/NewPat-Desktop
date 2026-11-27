"""Exercise report selection and archived results using Letizia's two upstream examples."""
import json
from pathlib import Path
from shutil import copytree

import pytest

from newpat.desktop.analysis_report import report_cases
from newpat.desktop.report_bundle import build_bundle
from newpat.desktop.results import ResultsStore
from test_gui_results import artifact, make_run, validation, write_json


EXAMPLES = Path(__file__).parent / "fixtures/fetal_sex/outputs"


@pytest.mark.parametrize(("example", "expected", "means"), [
    ("Female_fetus", "Female", [20, 20, 0]), ("Male_fetus", "Male", [20, 2.5, 30]),
])
def test_archive_and_pdf_show_the_recorded_classification(tmp_path, example, expected, means):
    mapping = [{"sample_id": role, "biological_id": "maternal", "original_path": role + ".txt"}
               for role in ("autosomes", "x", "y")]
    run = make_run(tmp_path, "fetal-sex", mapping=mapping)
    copytree(EXAMPLES / example, run / "output", dirs_exist_ok=True)
    metadata = json.loads((run / "run.json").read_text())
    metadata["parameters"]["fetal_sex"] = {"sample_id": "maternal"}
    write_json(run / "run.json", metadata)
    store = ResultsStore(tmp_path, language="en")
    for marker in ("DNP", "SNP"):
        assert store.list_runs(marker=marker)["runs"][0]["sample_count"] == 1
        group, = store.overview("example", marker=marker)["modules"]
        assert group["marker"] == "DNP+SNP"
    case, = report_cases(store, "example")
    bundle = build_bundle(store, "example", [case["id"]], "combined")
    short, = bundle["summary_results"]
    detail, = bundle["results"]
    assert short["subject"] == "maternal"
    assert short["headline"] == "Estimated fetal sex: " + expected.lower()
    assert short["headline"] == detail["headline"]
    assert short["facts"][-1]["value"] == "10"
    assert "patern" not in json.dumps(bundle).lower()
    assert [p["y"] for p in detail["charts"][0]["points"]] == means
    assert [table["title"] for table in detail["tables"]] == [
        "Informative autosomal sites", "Informative X sites", "Chromosome Y sites"]
    assert "same maternal cell-free DNA sample" in detail["result_basis"]


def test_undetermined_missing_and_modified_results_remain_distinct(tmp_path):
    run = make_run(tmp_path, "fetal-sex")
    copytree(EXAMPLES / "Male_fetus", run / "output", dirs_exist_ok=True)
    path = run / "output/Fetal_sex_summary.txt"
    store = ResultsStore(tmp_path)
    for recorded, expected in [("Undetermined", "Sesso fetale indeterminato"), ("NA", "Risultato non disponibile")]:
        lines = path.read_text().splitlines()
        row = lines[1].split("\t")
        row[lines[0].split("\t").index("Fetal_sex")] = recorded
        path.write_text(lines[0] + "\n" + "\t".join(row) + "\n")
        case, = report_cases(store, "example")
        assert build_bundle(store, "example", [case["id"]], "summary")["results"][0]["headline"] == expected
    validation(run, "fetal-sex", {"summary": artifact(run, "output/Fetal_sex_summary.txt")})
    path.write_text(path.read_text().replace("\tNA\t", "\tM\t", 1))
    assert not report_cases(store, "example")


def test_combined_experiment_keeps_fetal_sex_and_contamination_in_one_ordered_bundle(tmp_path):
    from test_gui_results import table

    run = make_run(tmp_path, "analysis")
    roles = {"autosomes": "auto", "x": "chromX", "y": "chromY"}
    samples = [{"id": sid, "path": f"/input/{sid}.tsv", "kind": "snp-table" if role == "y" else "dnp-table"}
               for role, sid in roles.items()]
    plan_steps = [
        {"id": "cont", "workflow": "contamination",
         "inputs": {"samples": [{"sample": "auto"}], "panel": "/input/panel.tsv"}, "parameters": {}},
        {"id": "sex", "workflow": "fetal-sex", "inputs": roles, "parameters": {}},
    ]
    steps = [{"id": s["id"], "workflow": s["workflow"]} for s in plan_steps]
    metadata = json.loads((run / "run.json").read_text())
    metadata["parameters"] = {
        "plan": {"schema_version": 1, "samples": samples, "steps": plan_steps},
        "expected_steps": steps,
        "sample_mapping": [{"sample_id": s["id"], "container_path": s["path"], "original_path": s["path"],
                            "biological_id": "maternal"} for s in samples],
        "fetal_sex": {"sample_id": "maternal"},
    }
    write_json(run / "run.json", metadata)
    out = run / "output/workflow"
    write_json(out / "workflow-state.json", {"schema_version": 1, "interface": "workflow-plan-execution-v2",
               "status": "succeeded", "steps": [{**s, "status": "succeeded"} for s in steps]})
    copytree(EXAMPLES / "Male_fetus", out / "steps/sex/output")
    table(out / "steps/cont/output/contamination_summary.txt",
          ["individuo", "informative_sites", "mean_contamination"], [["auto", "2", "0.01"]])
    store = ResultsStore(tmp_path, language="en")
    cases = report_cases(store, "example")
    assert [case["module"] for case in cases] == ["contamination", "fetal-sex"]
    bundle = build_bundle(store, "example", [case["id"] for case in reversed(cases)], "combined")
    for key in ("results", "summary_results"):
        assert [row["headline"] for row in bundle[key]] == ["Estimated fetal sex: male", "Estimated mean contamination: 1 %"]
