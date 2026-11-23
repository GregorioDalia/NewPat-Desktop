"""Desktop result contracts: native identity, units, paging and scoped access."""
import csv
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from nipat.gui.results import ResultsStore, column_description
from nipat.gui.app import DesktopApplication


@pytest.fixture
def archive(tmp_path):
    root = tmp_path / "runs"
    root.mkdir()
    return root


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def table(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out, delimiter="," if path.suffix == ".csv" else "\t")
        writer.writerow(columns)
        writer.writerows(rows)


def make_run(root, module="contamination", name="example", marker="DNP", mapping=None):
    run = root / name
    run.mkdir(parents=True)
    write_json(run / "run.json", {"schema_version": 1, "workflow": module, "status": "succeeded",
               "run_name": "Esperimento è", "started_at": "2026-11-15T10:00:00Z", "finished_at": "2026-11-15T10:01:00Z",
               "source": {"nipat_version": "0.8.99"}, "parameters": {"marker_type": marker, "sample_mapping": mapping or [
                   {"sample_id": "A", "original_path": r"D:\campioni\Campione è.txt"}]}})
    (run / "output").mkdir()
    return run


def validation(run, module, artifacts, warnings=None):
    write_json(run / "work/scientific-validation.json", {"schema_version": 1, "workflow": module,
               "status": "passed", "artifacts": artifacts, "quality_warnings": warnings or []})


def artifact(run, relative, **kw):
    return {"path": relative, "sha256": hashlib.sha256((run / relative).read_bytes()).hexdigest(), **kw}


def file_named(store, name, run="example"):
    return next(f for f in store.files(run) if f["name"] == name)


def test_original_precision_zero_and_na_survive_table_and_summary(archive):
    run = make_run(archive)
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination", "sd_contamination"],
          [["native-A", "2", "0", "0.0353553390593274"], ["native-B", "0", "NA", "NA"]])
    table(run / "output/contamination_native-A.txt", ["chr", "pos1", "pos2", "contamination"], [["chr1", "1", "2", "0.1234567890123456789"]])
    validation(run, "contamination", {"contamination-tables": [artifact(run, "output/contamination_native-A.txt", sample="A", native_name="native-A")]})
    store = ResultsStore(archive)
    f = file_named(store, "contamination_summary.txt")
    page = store.table("example", f["id"])
    assert page["rows"][0]["sd_contamination"] == "0.0353553390593274"
    entries = store.overview("example")["modules"][0]["entries"]
    zero, missing = [e["metrics"][0] for e in entries]
    assert zero["value"] == "0" and zero["available"] and zero["scale"] == 100
    assert missing["value"] is None and not missing["available"] and missing["raw_value"] == "NA"
    assert entries[0]["sample_id"] == "A" and entries[0]["sample_label"] == "Campione è.txt"
    assert entries[0]["metrics"][1]["unit"] == "punti %"
    assert store.file_path("example", f["id"]).read_bytes() == (run / "output/contamination_summary.txt").read_bytes()


def test_large_table_pagination_filters_and_original_row_numbers(archive):
    run = make_run(archive, "snp-call", marker="SNP")
    table(run / "output/SNPcall_output.txt", ["chr", "pos", "GT", "total_count"],
          [["chr1" if i % 2 else "chr2", i + 1, "NA" if i % 3 == 0 else "0/1", "100"] for i in range(1201)])
    store = ResultsStore(archive)
    f = file_named(store, "SNPcall_output.txt")
    page = store.table("example", f["id"], offset=20, limit=10, query="chr1", filters={"GT": ["NA"]})
    assert page["total"] == 1201 and page["matched"] == 200 and page["has_more"]
    assert len(page["rows"]) == 10 and page["row_numbers"][0] == 123
    assert page["rows"][0] == {"chr": "chr1", "pos": "124", "GT": "NA", "total_count": "100"}
    stats = store.overview("example")["modules"][0]["entries"][0]
    assert stats["site_count"] == 1201 and stats["unassigned"] == 401 and stats["read_observations"] == 120100
    with pytest.raises(ValueError):
        store.table("example", f["id"], limit=1001)
    with pytest.raises(ValueError):
        store.table("example", f["id"], filters={"not-a-column": "x"})


def test_invalid_tables_and_mid_read_mutation_are_rejected(archive, monkeypatch):
    run = make_run(archive)
    target = run / "output/bad.tsv"
    target.write_text("a\ta\n1\t2\n")
    store = ResultsStore(archive)
    f = file_named(store, "bad.tsv")
    with pytest.raises(ValueError, match="duplicate"):
        store.table("example", f["id"])
    target.write_text("a\tb\n1\n")
    with pytest.raises(ValueError, match="completa"):
        store.table("example", f["id"])
    target.write_text("a\tb\n1\t2\n")
    from nipat.gui import results
    original = results._rows
    def changed(path):
        yield from original(path)
        path.write_text("a\tb\n3\t4\nextra\trow\n")
    monkeypatch.setattr(results, "_rows", changed)
    with pytest.raises(ValueError, match="cambiato"):
        store.table("example", f["id"])


def test_native_dnp_aliases_map_to_recorded_samples_not_list_position(archive):
    mapping = [{"sample_id": "paternal", "original_path": "Father.bam"},
               {"sample_id": "maternal", "original_path": "Mother.bam"}]
    run = make_run(archive, "dnp-call", mapping=mapping)
    for num, gt in [(1, "0/0"), (2, "1/1")]:
        table(run / f"output/individual_outputs/full_output_sample_{num:04d}.txt", ["chr", "pos1", "pos2", "GT", "total_count"], [["chr1", 1, 2, gt, 25]])
        path = run / f"output/plots/sample_{num:04d}/plot.pdf"
        path.parent.mkdir(parents=True); path.write_bytes(b"%PDF-test")
    table(run / "output/summary/output_AllGenotypes.txt", ["chr", "pos1", "pos2", "GT_sample_0001", "GT_sample_0002"], [["chr1", 1, 2, "0/0", "1/1"]])
    validation(run, "dnp-call", {"dnp-tables": [
        artifact(run, "output/individual_outputs/full_output_sample_0001.txt", sample="maternal", native_name="sample_0001"),
        artifact(run, "output/individual_outputs/full_output_sample_0002.txt", sample="paternal", native_name="sample_0002")]})
    store = ResultsStore(archive)
    first = store.overview("example")["modules"][0]["entries"][0]
    assert first["sample_id"] == "maternal" and first["label"] == "Mother.bam"
    plots = [f for f in store.files("example") if f["kind"] == "pdf"]
    assert [p["sample_id"] for p in plots] == ["maternal", "paternal"]
    assert first["plot_file_ids"] == [plots[0]["id"]]
    matrix = file_named(store, "output_AllGenotypes.txt")
    columns = store.table("example", matrix["id"])["columns"]
    assert columns[3]["label"] == "Genotipo · Mother.bam"


def test_cpi_log_scale_family_and_named_cutoff_curve_mapping(archive):
    mapping = [{"sample_id": "MotherM", "original_path": "Materna.txt"}, {"sample_id": "FatherF", "original_path": "Paterno.txt"}]
    run = make_run(archive, "cpi", mapping=mapping)
    name = "MotherM-FatherF_DNPs"
    table(run / "output/Summary_FetalFraction_CPI.csv", ["Pair", "Cutoff", "Median_fetal_fraction_percent", "CPI_medianFF", "N_sites_mother", "N_sites_father"],
          [[name, "Panel A", "6", "0.602", "3", "3"], [name, "Panel B", "NA", "NA", "0", "0"]])
    curves = []
    for n, cutoff in enumerate(["Panel A", "Panel B"], 1):
        relative = f"output/curves/{name}_panel_{n}.tsv"
        table(run / relative, ["Iteration", "log_CPI", "CPI"], [["2", "1.30102999566398", "20"]] if n == 1 else [])
        curves.append(artifact(run, relative, cutoff=cutoff))
    validation(run, "cpi", {"cpi-pairs": [{"pair": "M:F", "native_pair": name, "mother": {"sample": "M"}, "father": {"sample": "F"}, "curves": curves}]})
    store = ResultsStore(archive)
    entries = store.overview("example")["modules"][0]["entries"]
    assert entries[0]["family_label"] == "Materna.txt / Paterno.txt"
    assert entries[0]["metrics"][1]["unit"] == "log10"
    assert entries[0]["metrics"][1]["label"] == "log₁₀(CPI) alla frazione fetale mediana"
    assert entries[0]["metrics"][0]["scale"] == 1 and entries[0]["metrics"][0]["unit"] == "%"
    assert entries[0]["curve_file_ids"] != entries[1]["curve_file_ids"]
    assert all(len(e["curve_file_ids"]) == 1 for e in entries)
    assert entries[1]["metrics"][1]["value"] is None


def test_cpin_selection_and_interval_endpoints_stay_separate(archive):
    run = make_run(archive, "cpin")
    name = "MotherM-FatherF-ChildC_DNPs"
    columns = ["Trio", "Analysis", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"]
    table(run / "output/Summary_Postnatal_CPI.txt", columns, [
        [name, "all_compatible_sites", "0.00046474155109453", "-3.33278849686833", "3", "2", "1"],
        [name, "heterozygous_child_sites", "0.000278844930656718", "-3.55463724648469", "2", "1", "1"]])
    site = f"output/sites/{name}_sites.tsv"
    table(run / site, ["chr", "pos1", "pos2", "Status", "Paternity_Index"], [["chr1", 1, 2, "quality_filter", "NA"]])
    analyses = []
    for analysis in ["all_compatible_sites", "heterozygous_child_sites"]:
        relative = f"output/curves/{name}_{analysis}_curve.tsv"
        table(run / relative, ["Min_child_reads", "Through_min_child_reads", "Log10_CPI"], [["2", "5", "-3.33278849686833"], ["6", "6", "-3.42969850987639"], ["7", "10", "0.221848749616356"]])
        analyses.append({"analysis": analysis, "curve": artifact(run, relative)})
    validation(run, "cpin", {"cpin-trios": [{"trio": "family", "native_trio": name, "analyses": analyses, "sites": artifact(run, site)}]})
    store = ResultsStore(archive)
    entries = store.overview("example")["modules"][0]["entries"]
    assert len(entries) == 2 and entries[0]["analysis"] != entries[1]["analysis"]
    assert entries[0]["curve_file_ids"] != entries[1]["curve_file_ids"]
    page = store.table("example", entries[0]["curve_file_ids"][0])
    assert [(r["Min_child_reads"], r["Through_min_child_reads"]) for r in page["rows"]] == [("2", "5"), ("6", "6"), ("7", "10")]
    assert column_description("Status")["values"]["quality_filter"] == "Filtro di qualità non superato"


@pytest.mark.parametrize("marker", ["DNP", "SNP"])
def test_interactive_prenatal_curve_is_complete_and_keeps_original_values(archive, marker):
    run = make_run(archive, "cpi", marker=marker)
    native = "MotherM-FatherF_" + marker + "s"
    summary = run / "output/Summary_FetalFraction_CPI.csv"
    table(summary, ["Pair", "Median_fetal_fraction_percent", "CPI_medianFF"], [[native, "6", "0.602"]])
    relative = f"output/curves/{native}_panel_1.tsv"
    columns = ["Iteration", "InfSites_mother", "InfSites_father", "CPI", "log_CPI", "Mismatch", "NotMismatch", "Cutoff"]
    rows = [[str(i + 2), "10", "9", "Inf" if i == 0 else "NA", "0.1234567890123456789" if i == 0 else "NA", "1", "8", "ALL"]
            for i in range(1005)]
    table(run / relative, columns, rows)
    validation(run, "cpi", {"cpi-pairs": [{"pair": "M:F", "native_pair": native,
        "mother": {"sample": "M"}, "father": {"sample": "F"},
        "curves": [artifact(run, relative, cutoff=None)]}]})
    store = ResultsStore(archive)
    entry = store.overview("example")["modules"][0]["entries"][0]
    assert len(entry["curve_file_ids"]) == 1  # all-sites mode has no Cutoff in the summary
    original = (run / relative).read_bytes()
    curve = store.curve("example", entry["curve_file_ids"][0])
    assert len(curve["rows"]) == 1005 and curve["has_more"] is False
    assert curve["rows"][0] == dict(zip(columns, rows[0]))
    assert curve["rows"][-1] == dict(zip(columns, rows[-1]))
    assert curve["row_numbers"][-1] == 1004
    assert curve["curve"] == {"x_key": "Iteration", "y_key": "log_CPI", "through_key": None, "interval_endpoints": None}
    assert curve["columns"][0]["label"] == "Letture fetali minime"
    assert (run / relative).read_bytes() == original


def test_interactive_postnatal_curve_keeps_intervals_and_site_counts(archive):
    run = make_run(archive, "cpin")
    relative = "output/curves/family_all_compatible_sites_curve.tsv"
    columns = ["Min_child_reads", "Through_min_child_reads", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites"]
    rows = [["2", "5", "-3.33278849686833", "3", "2", "1"],
            ["6", "8", "0", "1", "1", "0"]]
    table(run / relative, columns, rows)
    store = ResultsStore(archive)
    curve = store.curve("example", file_named(store, Path(relative).name)["id"])
    assert curve["rows"] == [dict(zip(columns, row)) for row in rows]
    assert curve["curve"]["interval_endpoints"] == "inclusive"
    assert curve["curve"]["through_key"] == "Through_min_child_reads"
    assert curve["total"] == 2  # no expansion, interpolation or repeated thresholds


def test_interactive_curves_reject_partial_or_unbounded_reads_but_keep_original_table(archive, monkeypatch):
    from nipat.gui import results

    run = make_run(archive, "cpi")
    path = run / "output/curves/family_panel_1.tsv"
    table(path, ["Iteration", "log_CPI"], [[2, "1.1234567890123456789"], [3, "NA"]])
    store = ResultsStore(archive, language="en")
    file_id = file_named(store, path.name)["id"]
    monkeypatch.setattr(results, "_MAX_CURVE_ROWS", 1)
    with pytest.raises(ValueError, match="full table or original PDF"):
        store.curve("example", file_id)
    assert store.table("example", file_id)["total"] == 2
    monkeypatch.setattr(results, "_MAX_CURVE_ROWS", 20)
    monkeypatch.setattr(results, "_MAX_CURVE_BYTES", 2)
    with pytest.raises(ValueError, match="interactive chart limit"):
        store.curve("example", file_id)
    monkeypatch.setattr(results, "_MAX_CURVE_BYTES", 1024)
    original_rows = results._rows

    def changing_rows(selected):
        yield from original_rows(selected)
        selected.write_text("Iteration\tlog_CPI\n2\t8\n")

    monkeypatch.setattr(results, "_rows", changing_rows)
    with pytest.raises(ValueError, match="changed while reading"):
        store.curve("example", file_id)


def test_interactive_curve_requires_matching_schema_and_scoped_curve_file(archive, tmp_path):
    run = make_run(archive, "cpin")
    path = run / "output/curves/family_curve.tsv"
    table(path, ["Iteration", "log_CPI"], [[2, "1"]])
    store = ResultsStore(archive)
    file_id = file_named(store, path.name)["id"]
    with pytest.raises(ValueError, match="colonne richieste"):
        store.curve("example", file_id)
    table(run / "output/not-a-curve.tsv", ["Min_child_reads", "Through_min_child_reads", "Log10_CPI"], [[2, 4, "1"]])
    with pytest.raises(ValueError, match="non è una curva"):
        store.curve("example", file_named(store, "not-a-curve.tsv")["id"])
    for run_id, identifier in [("../outside", file_id), ("example", "../private")]:
        with pytest.raises(ValueError):
            store.curve(run_id, identifier)
    path.unlink()
    outside = tmp_path / "secret.tsv"
    outside.write_text("PRIVATE")
    try:
        path.symlink_to(outside)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValueError):
        store.curve("example", file_id)


def test_scoped_reads_reject_links_traversal_and_unregistered_ids(archive, tmp_path):
    run = make_run(archive)
    secret = tmp_path / "secret.tsv"
    secret.write_text("private\n42\n")
    (run / "output/linked.tsv").symlink_to(secret)
    (run / "output/external").symlink_to(tmp_path, target_is_directory=True)
    store = ResultsStore(archive)
    assert not any(f["name"] == "linked.tsv" for f in store.files("example"))
    for run_id in ["../", str(tmp_path), "example/../../", r"C:\Windows", "imported-" + "a" * 32]:
        with pytest.raises(ValueError):
            store.get_run(run_id)
    with pytest.raises(ValueError):
        store.file_path("example", "../../secret.tsv")
    forged = hashlib.sha256(b"output/linked.tsv").hexdigest()[:32]
    with pytest.raises(ValueError):
        store.file_path("example", forged)
    unrelated = run / "work/secret.tsv"
    unrelated.parent.mkdir(); unrelated.write_text("do not expose")
    forged = hashlib.sha256(b"work/secret.tsv").hexdigest()[:32]
    with pytest.raises(ValueError):
        store.file_path("example", forged)
    (run / "work/scientific-validation.json").symlink_to(secret)
    assert not any(f["relative_path"] == "work/scientific-validation.json" for f in store.files("example"))
    forged = hashlib.sha256(b"work/scientific-validation.json").hexdigest()[:32]
    with pytest.raises(ValueError):
        store.file_path("example", forged)


def test_import_registers_in_place_persists_and_never_changes_native_files(archive, tmp_path):
    external = tmp_path / "external"
    run = make_run(external, "snp-call", marker="SNP")
    table(run / "output/SNPcall_output.txt", ["chr", "pos", "GT", "total_count"], [["chr1", "5", "0/1", "12"]])
    before = {p.relative_to(external).as_posix(): p.read_bytes() for p in external.rglob("*") if p.is_file()}
    store = ResultsStore(archive)
    imported = store.register_run(external)
    assert imported["count"] == 1 and imported["imported"][0].startswith("imported-")
    fresh = ResultsStore(archive)
    run_id = fresh.list_runs()["runs"][0]["id"]
    assert run_id == imported["imported"][0]
    f = file_named(fresh, "SNPcall_output.txt", run_id)
    assert fresh.file_path(run_id, f["id"]) == run / "output/SNPcall_output.txt"
    assert before == {p.relative_to(external).as_posix(): p.read_bytes() for p in external.rglob("*") if p.is_file()}
    assert store.register_run(run)["imported"] == [run_id]
    assert fresh.list_runs()["total"] == 1
    moved = tmp_path / "moved"
    external.rename(moved)
    external.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError, match="importata"):
        fresh.file_path(run_id, f["id"])


@pytest.mark.parametrize("workflow", [False, True], ids=["standalone", "gui-workflow"])
def test_export_roundtrip_preserves_scientific_identity_details_and_warnings(archive, tmp_path, workflow):
    run = make_run(archive, "analysis" if workflow else "contamination")
    output = run / ("output/workflow/steps/contamination/output" if workflow else "output")
    table(output / "contamination_summary.txt",
          ["individuo", "informative_sites", "mean_contamination", "sd_contamination"],
          [["native-A", "2", "0.02", "0.01"]])
    sites = output / "contamination_native-A.txt"
    table(sites, ["chr", "pos1", "pos2", "contamination"], [["chr1", "1", "2", "0.02"]])
    warning = {"code": "input.example", "message": "Original scientific warning"}
    if workflow:
        from test_workflow_five_modules import plan_for
        from nipat_scientific.plan import validate_plan
        plan = validate_plan(plan_for("SNP", called=False))["plan"]
        steps = [{"id": step["id"], "workflow": step["workflow"], "status": "succeeded", "artifacts": {}}
                 for step in plan["steps"]]
        metadata = json.loads((run / "run.json").read_text(encoding="utf-8"))
        metadata["parameters"] = {"plan": plan,
            "expected_steps": [{"id": step["id"], "workflow": step["workflow"]} for step in steps],
            "sample_mapping": [{"sample_id": s["id"], "original_path": s["id"] + ".tsv", "container_path": s["path"]}
                               for s in plan["samples"]]}
        write_json(run / "run.json", metadata)
        relative = sites.relative_to(run / "output/workflow").as_posix()
        steps[0]["artifacts"] = {"contamination-tables": [{"path": relative, "sample": "mother", "native_name": "native-A"}]}
        steps[0]["quality_warnings"] = [warning]
        write_json(run / "output/workflow/workflow-state.json", {"schema_version": 1,
                   "interface": "workflow-plan-execution-v2", "status": "succeeded", "steps": steps})
        write_json(run / "gui.json", {"schema_version": 1, "name": "GUI experiment", "draft": {"caller": "tables"}})
    else:
        validation(run, "contamination", {"contamination-tables": [
            artifact(run, sites.relative_to(run).as_posix(), sample="A", native_name="native-A")]}, [warning])
    (run / "work").mkdir(exist_ok=True)
    (run / "work/unrelated.tsv").write_text("private\n42\n")
    store = ResultsStore(archive)
    before = store.overview("example")
    entry = next(g for g in before["modules"] if g["module"] == "contamination")["entries"][0]
    assert entry["sample_id"] == ("mother" if workflow else "A")
    assert entry["site_file_id"] is not None and before["warnings"]
    destination = tmp_path / "export.zip"
    application = DesktopApplication.__new__(DesktopApplication)
    application.host = SimpleNamespace(save_file=lambda *_: destination)
    application.service = SimpleNamespace(_results=lambda: store)
    from unittest.mock import patch
    with patch.object(store, "_file_descriptors", wraps=store._file_descriptors) as inventory:
        application.export_run({"run_id": "example"})
        assert inventory.call_count == 1
    restored_root = tmp_path / "restored"
    restored = restored_root / "example"
    with zipfile.ZipFile(destination) as exported:
        assert "work/unrelated.tsv" not in exported.namelist()
        assert ("output/workflow/workflow-state.json" if workflow else "work/scientific-validation.json") in exported.namelist()
        for name in exported.namelist():
            assert exported.read(name) == (run / name).read_bytes()
        exported.extractall(restored)
    reopened = ResultsStore(restored_root)
    assert reopened.get_run("example") == store.get_run("example")
    assert reopened.overview("example") == before
    assert reopened.table("example", entry["site_file_id"]) == store.table("example", entry["site_file_id"])


def test_gui_snapshot_is_readonly_name_and_query_use_human_labels(archive):
    run = make_run(archive)
    gui = {"schema_version": 1, "name": "Studio clinico è", "draft": {"samples": ["A"]}, "execution": {"parallel": "serial"}}
    write_json(run / "gui.json", gui)
    settings = {"schema_version": 1, "workflow": "contamination", "parameters": {"include_zero": True}}
    write_json(run / "output/scientific-settings.json", settings)
    before = (run / "gui.json").read_bytes()
    store = ResultsStore(archive)
    assert store.list_runs(query="studio CLINICO")["total"] == 1
    assert store.list_runs(query="Campione è")["total"] == 1
    record = store.get_run("example")
    assert record["name"] == "Studio clinico è" and record["draft"] == gui["draft"]
    assert record["settings"][0]["document"] == settings
    record["draft"]["samples"].append("B")
    assert (run / "gui.json").read_bytes() == before


def test_failed_runs_remain_failed_and_quality_warnings_are_visible(archive):
    run = make_run(archive)
    metadata = json.loads((run / "run.json").read_text(encoding="utf-8")); metadata["status"] = "failed"
    write_json(run / "run.json", metadata)
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination", "sd_contamination"], [["A", "0", "NA", "NA"]])
    validation(run, "contamination", {}, [{"code": "output.no_sites", "message": "Nessun sito informativo."}])
    store = ResultsStore(archive)
    assert store.get_run("example")["status"] == "failed"
    overview = store.overview("example")
    assert overview["modules"][0]["status"] == "failed"
    assert overview["warnings"][0]["message"] == "Nessun sito informativo."


def test_bilingual_field_labels_do_not_change_cell_values(archive):
    run = make_run(archive, "snp-call", marker="SNP")
    table(run / "output/SNPcall_output.txt", ["chr", "pos", "GT", "GL0", "resident_MB_end"], [["chr1", "10", "NA", "-1.23456789012345", "128.5"]])
    it, en = ResultsStore(archive), ResultsStore(archive, language="en")
    f = file_named(it, "SNPcall_output.txt")
    left, right = it.table("example", f["id"]), en.table("example", f["id"])
    assert left["rows"] == right["rows"]
    assert left["columns"][0]["label"] == "Cromosoma" and right["columns"][0]["label"] == "Chromosome"
    assert right["columns"][3]["unit"] == "ln"
    assert "not peak" in right["columns"][4]["description"]
    assert right["columns"][4]["unit"] == "MiB"
    assert right["file"]["label"] == "Counts and genotypes"
    metrics = en.overview("example")["modules"][0]["entries"][0]["metrics"]
    assert metrics[0]["label"] == "Sites in table"
    assert metrics[-1]["value"] is None and not metrics[-1]["available"]


def test_legacy_execution_snapshot_and_upset_meaning(archive):
    run = make_run(archive, "dnp-call")
    metadata = json.loads((run / "run.json").read_text(encoding="utf-8"))
    metadata["execution_options"] = {"cpus": 2, "memory_mb": 4096, "max_workers": 3}
    write_json(run / "run.json", metadata)
    (run / "output/DNPs_covered_UpSet_plot.pdf").write_bytes(b"%PDF-1.4\n")
    store = ResultsStore(archive, language="en")
    assert store.get_run("example")["execution"] == metadata["execution_options"]
    assert file_named(store, "DNPs_covered_UpSet_plot.pdf")["label"] == "Shared loci with assigned genotypes"


def test_read_totals_preserve_integer_precision_and_missingness(archive):
    run = make_run(archive, "snp-call", marker="SNP")
    path = run / "output/SNPcall_output.txt"
    table(path, ["chr", "pos", "GT", "total_count"],
          [["chr1", "10", "0/1", "9007199254740993"], ["chr1", "20", "NA", "1e2"]])
    store = ResultsStore(archive)
    entry = store.overview("example")["modules"][0]["entries"][0]
    assert entry["read_observations"] == 9007199254741093
    assert entry["metrics"][-1]["value"] == "9007199254741093"
    table(path, ["chr", "pos", "GT", "total_count"],
          [["chr1", "10", "0/1", "0"], ["chr1", "20", "NA", "NA"]])
    entry = store.overview("example")["modules"][0]["entries"][0]
    assert entry["read_observations"] is None and entry["sites_with_missing_read_counts"] == 1
    assert entry["metrics"][-1]["value"] is None


@pytest.mark.parametrize("explicit_marker", [True, False])
def test_validated_workflow_preserves_snp_branch_without_callers(archive, explicit_marker):
    from test_workflow_five_modules import plan_for
    from nipat_scientific.plan import validate_plan
    run = make_run(archive, "analysis")
    plan = validate_plan(plan_for("SNP", called=False))["plan"]
    if not explicit_marker:
        for step in plan["steps"]:
            del step["parameters"]["marker_type"]
    steps = [{"id": step["id"], "workflow": step["workflow"]} for step in plan["steps"]]
    metadata = json.loads((run / "run.json").read_text(encoding="utf-8"))
    metadata["parameters"] = {"plan": plan, "expected_steps": steps,
        "sample_mapping": [{"sample_id": s["id"], "original_path": s["id"] + ".tsv", "container_path": s["path"]}
                           for s in plan["samples"]]}
    write_json(run / "run.json", metadata)
    write_json(run / "output/workflow/workflow-state.json", {"schema_version": 1,
        "interface": "workflow-plan-execution-v2", "status": "succeeded",
        "steps": [{**step, "status": "succeeded", "artifacts": {}} for step in steps]})
    store = ResultsStore(archive)
    record = store.get_run("example")
    assert record["status"] == "succeeded"
    assert record["markers"] == ["SNP"]
    assert record["modules"] == ["contamination", "cpi", "cpin"]
    overview = store.overview("example")
    assert overview["not_run"] == ["dnp-call", "snp-call"]
    assert all(g["marker"] == "SNP" for g in overview["modules"])
    metadata["parameters"]["expected_steps"][0]["id"] = "../outside"
    write_json(run / "run.json", metadata)
    assert store.get_run("example")["status"] == "unreadable"
    assert store.overview("example")["warnings"]
