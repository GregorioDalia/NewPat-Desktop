"""Charts use values and identities from the selected archived result."""
import pytest

from newpat.desktop.analysis_report import build_report, report_cases
from newpat.desktop.report_charts import detail_charts
from newpat.desktop.results import ResultsStore
from test_gui_results import artifact, make_run, table, validation


def test_postnatal_site_indices_show_only_eligible_sites_including_true_zero():
    rows = [
        {"chr": "chr1", "pos1": "20", "pos2": "21", "Status": "eligible", "Paternity_Index": "2"},
        {"chr": "chr1", "pos1": "30", "pos2": "31", "Status": "quality_filter", "Paternity_Index": "17"},
        {"chr": "chr2", "pos1": "40", "pos2": "41", "Status": "eligible", "Paternity_Index": "0"},
        {"chr": "chr2", "pos1": "50", "pos2": "51", "Status": "eligible", "Paternity_Index": "Inf"},
    ]
    source = {"rows": rows, "total": 80}
    (chart,) = detail_charts("cpin", source, "it")
    assert [(p["label"], p["y"]) for p in chart["points"]] == [("chr1:20–21", 2), ("chr2:40–41", 0)]
    assert "prime 4 su 80" in chart["caption"]
    assert detail_charts("cpin", {"rows": [rows[1]], "total": 1}, "it") == []


@pytest.mark.parametrize("module", ["dnp-call", "snp-call"])
def test_sample_depth_shows_real_zero_and_omits_missing_negative_or_unrepresentable_counts(module):
    rows = [{"chr": "chr2", "pos": str(i + 1), "total_count": n}
            for i, n in enumerate(["20", "NA", "-1", "0", "0.2", "1E99"])]
    (chart,) = detail_charts(module, {"rows": rows, "total": len(rows)}, "en")
    assert [(p["label"], p["y"]) for p in chart["points"]] == [("chr2:1", 20), ("chr2:4", 0)]
    assert "first" not in chart["caption"] and "2 of 6" in chart["caption"]


def test_prenatal_support_selects_observed_thresholds_and_includes_endpoints_without_interpolating():
    rows = [{"Iteration": str(i), "InfSites_father": str(35 - i), "InfSites_mother": "99"} for i in range(35)]
    (chart,) = detail_charts("cpi", {"rows": rows, "total": 35}, "en")
    assert chart["kind"] == "bar" and len(chart["points"]) == 8
    assert chart["points"][0] == {"label": "Threshold 0", "x": 0, "y": 35}
    assert chart["points"][-1] == {"label": "Threshold 34", "x": 34, "y": 1}
    assert all(p["y"] == 35 - p["x"] for p in chart["points"])
    assert detail_charts("cpi", {"rows": [{"Iteration": "1", "log_CPI": "3.3"}], "total": 1}, "it") == []


def test_selected_contamination_estimate_uses_its_own_ref_alt_depth_and_rejects_changed_details(tmp_path):
    run = make_run(tmp_path)
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination"],
          [["a", 1, "0.04"], ["b", 1, "0.02"]])
    reports = []
    columns = ["chr", "pos1", "pos2", "N_REF", "N_ALT", "N_Other", "contamination"]
    for name, ref, alt in (("a", 96, 4), ("b", 49, 1)):
        relative = f"output/contamination_{name}.txt"
        table(run / relative, columns, [["chr4", 13, 14, ref, alt, 7, alt / (ref + alt)]])
        reports.append(artifact(run, relative, sample=name, native_name=name))
    validation(run, "contamination", {"tables": reports})
    store = ResultsStore(tmp_path, language="en")
    first, second = report_cases(store, "example")
    for case, expected in ((first, 100), (second, 50)):
        detail = build_report(store, "example", case["id"], detailed=True)
        assert detail["charts"][0] == detail["chart"]
        chart = detail["charts"][1]
        assert chart["points"] == [{"label": "chr4:13–14", "x": 0, "y": expected}]
    table(run / reports[1]["path"], columns, [["chr4", 13, 14, 0, 1, 99, 1]])
    stale = build_report(store, "example", second["id"], detailed=True)
    assert stale["table"] is None and stale["charts"] == []
    assert any("unavailable" in note for note in stale["notes"])
