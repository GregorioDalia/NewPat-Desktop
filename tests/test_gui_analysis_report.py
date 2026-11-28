"""Case selection and printed values through the normal archived ResultsStore."""
import json

import pytest

from newpat.desktop.analysis_report import build_report, report_case_options, report_cases
from newpat.desktop.results import ResultsStore
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
    assert {"result_basis", "archive_entry"}.isdisjoint(unavailable)
    zero = build_report(store, "example", first["id"], detailed=True)
    assert "No site in the sample met the criteria" in zero["result_basis"]
    report = build_report(store, "example", second["id"], detailed=True)
    assert report["case_id"] == second["id"]
    assert report["subject"] == "Campione è.txt" and "D:\\" not in json.dumps(report)
    assert report["facts"][0]["value"] == "0 %" and "0 %" in report["headline"]
    assert "across 2 informative sites" in report["result_basis"] and "reference or the alternative allele" in report["result_basis"]
    assert report["archive_entry"] == report["subject"] and "provenance" not in report
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
    assert short["headline"] == "Esito inconcludente"
    assert "permette di confermare o escludere" in short["explanation"] and short["chart"] is None
    extended = build_report(store, "example", first["id"], detailed=True)
    assert "arrotondato" in extended["explanation"]
    assert extended["chart"]["kind"] == "line"
    assert [p["y"] for p in extended["chart"]["points"]] == [0.0, 2.0]
    assert extended["table"]["rows"] == [["1", "0"], ["2", "2"]]
    assert extended["archive_entry"].endswith(" · Selected")
    assert "5 siti informativi" in extended["result_basis"] and "3 siti paterni candidati" in extended["result_basis"]
    assert "non specifica quanti siti" in extended["result_basis"]
    incomplete_curve = build_report(store, "example", second["id"], detailed=True)
    assert incomplete_curve["chart"] is None and incomplete_curve["notes"]


def test_postnatal_scalar_and_its_contributing_sites(tmp_path):
    run = make_run(tmp_path, "cpin", marker="SNP")
    name = "native-family"
    headers = ["Trio", "Marker_type", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"]
    row = [name, "SNP", "8", "0.903089986991944", "3", "3", "0"]
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpin",
                                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
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
    assert len(cases) == 1
    report = build_report(store, "example", cases[0]["id"], detailed=True)
    assert report["facts"][0]["value"] == "8"
    assert report["headline"] == "Inconclusive result"
    assert report["table"]["rows"][0][-1] == "2"
    assert report["charts"][-1]["title"] == "Contribution of individual sites to the CPI"
    assert report["charts"][-1]["points"][0]["y"] == 2
    assert report["subject"] == "trio1"
    assert "from 3 sites" in report["result_basis"] and "allele frequencies" in report["result_basis"]
    assert report["subjects"] == [{"label": "Maternal sample", "value": "A · Campione è.txt"}]
    assert report["date"] == "2026-11-15T10:01:00Z" and report["version"] == "0.8.99"
    # Subset rows do not identify which per-site observations belong in the report.
    table(run / "output/Summary_Postnatal_CPI.txt", ["Trio", "Analysis", "CPI", "Log10_CPI"],
          [[name, "heterozygous_child_sites", "8", "0.903089986991944"]])
    assert report_cases(store, "example") == []


@pytest.mark.parametrize(("module", "file"), [("dnp-call", "full_output_sample_0001.txt"), ("snp-call", "SNPcall_output.txt")])
def test_callers_and_summaries_report_only_completed_steps(tmp_path, module, file):
    run = make_run(tmp_path, module, marker="DNP" if module.startswith("dnp") else "SNP")
    table(run / "output" / file, ["chr", "pos", "GT", "total_count"],
          [["chr1", "100", "0/0", "5"], ["chr1", "200", "NA", "0"]])
    store = ResultsStore(tmp_path, language="en")
    (case,) = report_cases(store, "example")
    report = build_report(store, "example", case["id"], detailed=True)
    assert "1 of 2 sites" in report["headline"]
    assert "5 observations in total" in report["result_basis"]
    assert ("pairs of bases" if module == "dnp-call" else "individual bases") in report["result_basis"]
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
    assert "Nessun sito del trio" in report["result_basis"]
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
    assert "totale delle osservazioni sui siti non è disponibile" in result["result_basis"]


@pytest.mark.parametrize("lang", ["it", "en"])
def test_origin_uses_verified_prenatal_support_for_the_selected_panel_only(tmp_path, lang):
    run = make_run(tmp_path, "cpi")
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "Cutoff", "CPI_medianFF", "N_sites_mother", "N_sites_father"],
          [["family", "Full", "0.903", "3", "3"], ["family", "First", "0.301", "1", "1"]])
    curves = []
    for index, (panel, used) in enumerate([("Full", 2), ("First", 1)], 1):
        path = f"output/curves/family_panel_{index}.tsv"
        table(run / path, ["Iteration", "log_CPI"], [[1, 2]])
        curves.append(artifact(run, path, cutoff=panel, prenatal_support={"paternal_used_at_median": used}))
    validation(run, "cpi", {"cpi-pairs": [{"pair": "pair1", "native_pair": "family", "curves": curves}]})
    store = ResultsStore(tmp_path, language=lang)
    full, first = [build_report(store, "example", c["id"], detailed=True) for c in report_cases(store, "example")]
    assert full["archive_entry"].endswith(" · Full") and first["archive_entry"].endswith(" · First")
    assert ("3 siti informativi" if lang == "it" else "3 informative sites") in full["result_basis"]
    assert ("utilizzato 2 siti" if lang == "it" else "used 2 sites") in full["result_basis"]
    assert ("utilizzato 1 sito" if lang == "it" else "used 1 site") in first["result_basis"]


@pytest.mark.parametrize("lang", ["it", "en"])
def test_origin_does_not_treat_missing_contamination_counts_as_zero_or_repeat_a_stale_mean(tmp_path, lang):
    run = make_run(tmp_path)
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination"],
          [["first", "NA", "0.95"], ["second", "1", "NA"], ["third", "1", "0.03"]])
    store = ResultsStore(tmp_path, language=lang)
    unknown, no_estimate, single = [build_report(store, "example", c["id"], detailed=True)["result_basis"]
                                    for c in report_cases(store, "example")]
    assert ("non riporta un conteggio" if lang == "it" else "no usable count") in unknown
    assert "95" not in unknown and "0" not in unknown
    assert ("1 sito informativo" if lang == "it" else "1 informative site") in no_estimate
    assert ("non è disponibile" if lang == "it" else "unavailable") in no_estimate
    assert ("in 1 sito informativo" if lang == "it" else "across 1 informative site") in single


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
    from newpat.desktop import results

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


@pytest.mark.parametrize(("log_value", "category"), [
    ("0.903089986991944", "inconclusive"), ("3.9999998", "inconclusive"), ("4.0000002", "favorable"),
    ("-4.0000002", "unfavorable"), ("-4", "inconclusive"), ("4", "inconclusive"),
])
@pytest.mark.parametrize("lang", ["it", "en"])
def test_short_postnatal_report_classifies_native_values_before_display_and_keeps_indices_in_details(tmp_path, log_value, category, lang):
    run = make_run(tmp_path, "cpin")
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpin",
                                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
    validation(run, "cpin", {"settings": artifact(run, settings)})
    table(run / "output/Summary_Postnatal_CPI.txt", ["Trio", "CPI", "Log10_CPI", "N_sites", "Mismatch_probability"],
          [["T", str(10 ** float(log_value)), log_value, "123456", "0.001"]])
    store = ResultsStore(tmp_path, language=lang)
    (case,) = report_cases(store, "example")
    short = build_report(store, "example", case["id"])
    assert short["workflow"] == "cpin" and short["outcome_category"] == category
    assert [m["value"] for m in short["facts"]] == ["123456"]
    assert "CPI" not in short["headline"] + short["explanation"]
    if category == "inconclusive":
        assert short["headline"] == ("Esito inconcludente" if lang == "it" else "Inconclusive result")
    detail = build_report(store, "example", case["id"], detailed=True)
    assert detail["facts"][1]["value"] == (log_value.replace(".", ",") if lang == "it" else log_value)
    assert detail["headline"] == short["headline"] and "log₁₀" in detail["explanation"]


@pytest.mark.parametrize(("bounds", "estimate", "expected"), [
    ((-4, 4), "4.001", "favorable"), ((-4, 4), "-4.001", "unfavorable"),
    ((-3, -2), "-1", "inconclusive"), ((2, 3), "1", "inconclusive"), ((-3, -2), "0", "inconclusive"),
    ((-7, 9), "6", "inconclusive"), ((-4, 4), "4.000", "inconclusive"),
])
def test_prenatal_plot_guides_never_reverse_the_direction_of_evidence_or_assert_parentage(tmp_path, bounds, estimate, expected):
    run = make_run(tmp_path, "cpi")
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpi",
                                "parameters": {"log_cpi_lower": bounds[0], "log_cpi_upper": bounds[1]}})
    validation(run, "cpi", {"settings": artifact(run, settings)})
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "CPI_medianFF", "N_sites_mother", "N_sites_father"], [["family", estimate, 2, 2]])
    store = ResultsStore(tmp_path, language="en")
    (case,) = report_cases(store, "example")
    report = build_report(store, "example", case["id"])
    assert report["outcome_category"] == expected
    assert "CPI" not in report["explanation"] and "confirmed" not in report["headline"]
    if estimate == "4.000":
        assert "rounded" not in report["explanation"]
        assert "rounded prenatal value" in build_report(store, "example", case["id"], detailed=True)["explanation"]
    # Modifying a settings file whose digest was archived invalidates the comparison.
    write_json(run / settings, {"schema_version": 1, "workflow": "cpi",
                                "parameters": {"log_cpi_lower": -0.1, "log_cpi_upper": 0.1}})
    (new_case,) = report_cases(store, "example")
    assert build_report(store, "example", new_case["id"])["outcome_category"] == "nonassessable"


def test_revised_prenatal_pdf_uses_valid_sites_and_only_the_selected_hom_panel(tmp_path):
    run = make_run(tmp_path, "cpi", marker="SNP")
    settings = "output/scientific-settings.json"
    write_json(run / settings, {"schema_version": 1, "workflow": "cpi",
                                "parameters": {"log_cpi_lower": -4, "log_cpi_upper": 4}})
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "Cutoff", "N_sites_mother", "N_sites_father", "CPI_medianFF", "Include_homozygous_child",
           "Min_coverage", "N_sites_HET_child", "N_sites_HOM_child", "Log10_CPI_HET_child", "Log10_CPI_HOM_child"],
          [["pair", panel, 1, 0, "-5", "TRUE", "NA", 0, 1, 0, "-5"] for panel in ("First", "Second")])
    curves = []
    for i, panel in enumerate(("First", "Second"), 1):
        curve = f"output/curves/pair_panel_{i}.tsv"
        sites = f"output/pair_panel_{i}_HOM_child_sites.txt"
        table(run / curve, ["Iteration", "log_CPI", "InfSites_father", "NotMismatch", "Mismatch",
                            "N_sites_HET_child", "N_sites_HOM_child"], [[2, -5, 1, 0, 1, 0, 1]])
        table(run / sites, ["chr", "pos", "Paternal_allele", "Paternity_Index"], [["chr1", i * 10, "REF", "0.00001"]])
        curves.append(artifact(run, curve, cutoff=panel, hom_sites=artifact(run, sites)))
    validation(run, "cpi", {"cpi-pairs": [{"pair": "selection", "native_pair": "pair", "curves": curves}],
                            "settings": artifact(run, settings)})
    store = ResultsStore(tmp_path, language="en")
    cases = report_cases(store, "example")
    assert len(cases) == 2
    for i, case in enumerate(cases, 1):
        report = build_report(store, "example", case["id"], detailed=True)
        assert report["outcome_category"] == "unfavorable"
        assert "1 site contributed" in report["result_basis"]
        assert report["tables"][1]["rows"] == [["chr1", str(i * 10), "REF", "0.00001"]]
        assert [p["y"] for p in report["charts"][-1]["points"]] == [0, -5]
        assert {"label": "Minimum coverage per individual", "value": "Off"} in report["metrics"]
        assert any("experimental" in note for note in report["notes"])
        short = build_report(store, "example", case["id"])
        assert short["facts"] == [{"label": "DNA positions compared", "value": "1"}]
