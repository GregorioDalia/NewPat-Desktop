"""Case selection and printed values through the normal archived ResultsStore."""
import json

import pytest

from nipat.gui.analysis_report import build_report, report_case_options, report_cases
from nipat.gui.results import ResultsStore
from test_gui_results import artifact, make_run, table, validation, write_json


def test_contamination_separates_missing_and_zero_and_refuses_reordered_case(tmp_path):
    run = make_run(tmp_path)
    path = run / "output/contamination_summary.txt"
    headers = ["individuo", "informative_sites", "mean_contamination", "sd_contamination"]
    rows = [["first", "0", "NA", "NA"], ["second", "2", "0", "0"]]
    table(path, headers, rows)
    native = "output/contamination_second.txt"
    table(run / native, ["chr", "pos", "contamination"], [["chr1", "1", "0.03"], ["chr1", "2", "NA"]])
    validation(run, "contamination", {"tables": [artifact(run, native, sample="A", native_name="second")]})
    store = ResultsStore(tmp_path, language="en")
    first, second = report_cases(store, "example")
    unavailable = build_report(store, "example", first["id"])
    assert unavailable["headline"] == "Result unavailable"
    report = build_report(store, "example", second["id"], detailed=True)
    assert report["case_id"] == second["id"]
    assert report["subject"] == "Campione è.txt" and "D:\\" not in json.dumps(report)
    assert report["facts"][0]["value"] == "0 %" and "0 %" in report["headline"]
    assert report["table"]["rows"] == [["chr1", "1", "3 %"], ["chr1", "2", "Unavailable"]]
    assert [p["y"] for p in report["chart"]["points"]] == [3]
    table(path, headers, list(reversed(rows)))
    with pytest.raises(ValueError, match="Refresh the list"):
        build_report(store, "example", second["id"])


def test_prenatal_case_has_its_own_guides_and_curve(tmp_path):
    run = make_run(tmp_path, "cpi")
    names = ["Selected", "Another"]
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "Cutoff", "CPI_medianFF", "Median_fetal_fraction_percent", "N_sites_mother", "N_sites_father"],
          [["family", panel, "2", "5", "5", "3"] for panel in names])
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpi",
                                "parameters": {"log_cpi_lower": -2, "log_cpi_upper": 2}})
    curves = []
    for index, name in enumerate(names, 1):
        relative = f"output/curves/family_panel_{index}.tsv"
        table(run / relative, ["Iteration", "log_CPI"], [["1", "0"], ["2", "2" if index == 1 else "NA"]])
        curves.append(artifact(run, relative, cutoff=name))
    validation(run, "cpi", {"cpi-pairs": [{"pair": "pair1", "native_pair": "family", "curves": curves}],
                            "settings": artifact(run, settings)})
    store = ResultsStore(tmp_path)
    first, second = report_cases(store, "example")
    assert first["id"] != second["id"] and "Selected" in first["label"]
    short = build_report(store, "example", first["id"])
    assert short["headline"] == "Il risultato coincide con il limite superiore"
    assert "arrotondato" in short["explanation"] and short["chart"] is None
    extended = build_report(store, "example", first["id"], detailed=True)
    assert extended["chart"]["kind"] == "line"
    assert [p["y"] for p in extended["chart"]["points"]] == [0.0, 2.0]
    assert extended["table"]["rows"] == [["1", "0"], ["2", "2"]]
    incomplete_curve = build_report(store, "example", second["id"], detailed=True)
    assert incomplete_curve["chart"] is None and incomplete_curve["notes"]


@pytest.mark.parametrize("legacy", [False, True])
def test_postnatal_scalar_and_historical_site_selections(tmp_path, legacy):
    run = make_run(tmp_path, "cpin", marker="SNP")
    name = "native-family"
    headers = ["Trio", "Marker_type", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"]
    row = [name, "SNP", "8", "0.903089986991944", "3", "3", "0"]
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpin",
                                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
    if legacy:
        headers.append("Analysis")
        rows = [row + [subset] for subset in ["all_compatible_sites", "heterozygous_child_sites"]]
    else:
        headers.extend(["Mismatch_probability", "No_obligatory_allele_sites"])
        rows = [row + ["0.001", "0"]]
    table(run / "output/Summary_Postnatal_CPI.txt", headers, rows)
    site = f"output/{name}_sites.txt"
    table(run / site, ["chr", "pos", "Status", "Paternity_Index"], [["chr1", "35", "eligible", "2"]])
    validation(run, "cpin", {"cpin-trios": [{"trio": "trio1", "native_trio": name,
                                            "sites": artifact(run, site), "mother": {"sample": "A"}}],
                            "settings": artifact(run, settings)})
    store = ResultsStore(tmp_path, language="en")
    cases = report_cases(store, "example")
    assert len(cases) == (2 if legacy else 1)
    report = build_report(store, "example", cases[0]["id"], detailed=True)
    assert report["facts"][0]["value"] == "8"
    assert report["headline"] == ("Combined paternity index: 8" if legacy else "The result falls within the middle range")
    if legacy:
        assert report["table"] is None
    else:
        assert report["table"]["rows"][0][-1] == "2"
    assert report["subject"] == "trio1"
    assert report["subjects"] == [{"label": "Maternal sample", "value": "A · Campione è.txt"}]
    assert report["date"] == "2026-11-15T10:01:00Z" and report["version"] == "0.8.99"
    if legacy:
        assert all(case["selection"] for case in cases)


@pytest.mark.parametrize(("module", "file"), [("dnp-call", "full_output_sample_0001.txt"), ("snp-call", "SNPcall_output.txt")])
def test_callers_and_summaries_report_only_completed_steps(tmp_path, module, file):
    run = make_run(tmp_path, module, marker="DNP" if module.startswith("dnp") else "SNP")
    table(run / "output" / file, ["chr", "pos", "GT", "total_count"],
          [["chr1", "100", "0/0", "5"], ["chr1", "200", "NA", "0"]])
    store = ResultsStore(tmp_path, language="en")
    (case,) = report_cases(store, "example")
    report = build_report(store, "example", case["id"], detailed=True)
    assert "1 of 2 sites" in report["headline"]
    assert [p["y"] for p in report["chart"]["points"]] == [1, 0, 0, 1]
    assert report["table"]["rows"][1][-2:] == ["Unavailable", "0"]
    metadata = run / "run.json"
    write_json(metadata, {**json.loads(metadata.read_bytes()), "status": "interrupted"})
    assert not report_cases(store, "example")
    with pytest.raises(ValueError, match="Select a completed result"):
        build_report(store, "example", case["id"])


def test_report_does_not_infer_a_positive_result_with_no_sites_or_export_host_paths(tmp_path):
    run = make_run(tmp_path, "cpin", mapping=[{"sample_id": "A", "original_path": "/patients/secret/source.bam",
                                               "display_name": r"C:\private\patient\mother.bam"}])
    write_json(run / "gui.json", {"schema_version": 1, "name": "/private/people/Case X"})
    table(run / "output/Summary_Postnatal_CPI.txt",
          ["Trio", "Marker_type", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites",
           "Mismatch_probability", "extra_unreviewed_source_path"],
          [["native", "DNP", "8888", "3.9", "0", "0", "0", "0.001", "/private/people/secret.txt"]])
    validation(run, "cpin", {"cpin-trios": [{"trio": "family", "native_trio": "native", "mother": {"sample": "A"}}]})
    store = ResultsStore(tmp_path, language="it")
    (case,) = report_cases(store, "example")
    assert "private" not in case["label"]
    report = build_report(store, "example", case["id"], detailed=True)
    assert "private" not in json.dumps(report) and "8888" not in json.dumps(report)
    assert report["run_name"] == "Case X" and "mother.bam" in report["subjects"][0]["value"]
    assert report["headline"] == "Risultato non disponibile"
    assert report["facts"][0]["value"] == "Non disponibile"
    assert report["facts"][2]["value"] == "0" and "insufficiente" in report["explanation"]


def test_unrecognized_genotypes_are_not_counted_as_zero(tmp_path):
    run = make_run(tmp_path, "snp-call", marker="SNP")
    table(run / "output/SNPcall_output.txt", ["chr", "pos", "GT"], [["foo", 1, "unrecognized"]])
    store = ResultsStore(tmp_path)
    (case,) = report_cases(store, "example")
    result = build_report(store, "example", case["id"], detailed=True)
    assert result["headline"] == "Risultato non disponibile" and result["chart"] is None
    assert result["facts"][0]["value"] == "Non disponibile" and result["facts"][1]["value"] == "1"


def test_prenatal_chart_does_not_interpolate_across_an_absent_threshold(tmp_path):
    run = make_run(tmp_path, "cpi")
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "CPI_medianFF", "N_sites_mother", "N_sites_father"], [["family", "2", "5", "3"]])
    path = "output/curves/family_panel_1.tsv"
    table(run / path, ["Iteration", "log_CPI"], [[1, 2], [5, 3]])
    validation(run, "cpi", {"cpi-pairs": [{"pair": "one", "native_pair": "family",
                                         "curves": [artifact(run, path, cutoff=None)]}]})
    store = ResultsStore(tmp_path)
    (case,) = report_cases(store, "example")
    result = build_report(store, "example", case["id"], detailed=True)
    assert result["chart"] is None and result["table"]["rows"] == [["1", "2"], ["5", "3"]]


def test_large_summary_exposes_partial_list_without_blocking_visible_results(tmp_path, monkeypatch):
    from nipat.gui import results

    run = make_run(tmp_path)
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination"],
          [["first", 2, "0.02"], ["second", 1, "0.05"]])
    monkeypatch.setattr(results, "_MAX_SUMMARY", 1)
    store = ResultsStore(tmp_path, language="en")
    options = report_case_options(store, "example")
    assert len(options["cases"]) == 1
    assert "Contamination · DNP" in options["notes"][0] and "original table" in options["notes"][0]
    result = build_report(store, "example", options["cases"][0]["id"])
    assert result["subject"] == "first" and result["facts"][0]["value"] == "2 %"


@pytest.mark.parametrize(("log_value", "expected_display"), [
    ("0.903089986991944", "≈ 0,903"), ("3.9999998", "3,9999998"), ("4.0000002", "4,0000002"),
])
def test_short_report_abbreviates_measures_only_when_the_guide_comparison_is_preserved(tmp_path, log_value, expected_display):
    run = make_run(tmp_path, "cpin")
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpin",
                                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
    validation(run, "cpin", {"settings": artifact(run, settings)})
    table(run / "output/Summary_Postnatal_CPI.txt", ["Trio", "CPI", "Log10_CPI", "N_sites", "Mismatch_probability"],
          [["T", "8", log_value, "123456", "0.001"]])
    store = ResultsStore(tmp_path)
    (case,) = report_cases(store, "example")
    short = build_report(store, "example", case["id"])
    assert [m["value"] for m in short["facts"]] == ["8", expected_display, "123456"]
    detail = build_report(store, "example", case["id"], detailed=True)
    assert detail["facts"][1]["value"] == log_value.replace(".", ",")
    assert detail["headline"] == short["headline"]
