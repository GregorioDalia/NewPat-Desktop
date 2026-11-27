"""Case-bound IGV views use native sites, recorded sample assignments and pinned local files."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from newpat.experiments.tracking import file_evidence
from newpat.desktop.analysis_report import report_cases
from newpat.desktop.app import DesktopApplication
from newpat.desktop.results import ResultsStore
from test_gui_igv import _bam, _reference
from test_gui_results import artifact, make_run, table, validation, write_json


def sources(root, module="dnp-call", marker="DNP"):
    fasta = _reference(root)
    bams = {name: _bam(root, name=name) for name in ("Mother", "Father", "Child", "Other")}
    samples = [{"id": name, "path": str(path), "kind": "bam"} for name, path in bams.items()]
    mapping = [{"sample_id": s["id"], "original_path": s["path"]} for s in samples]
    run = make_run(root, module, marker=marker, mapping=mapping)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    write_json(run / "gui.json", {"schema_version": 1, "draft": {"reference": str(fasta), "samples": samples,
               "reference_genome": {"fasta": str(fasta), "index": str(fasta) + ".fai", "build": "custom",
                                    "fasta_sha256": digest(fasta), "index_sha256": digest(Path(str(fasta) + ".fai"))}}})
    metadata = json.loads((run / "run.json").read_bytes())
    metadata["inputs"] = [file_evidence(p) for p in (fasta, Path(str(fasta) + ".fai"))]
    metadata["inputs"] += [file_evidence(p) for bam in bams.values() for p in (bam, Path(str(bam) + ".bai"))]
    write_json(run / "run.json", metadata)
    store = ResultsStore(root, language="en")
    registrations = []

    def register(path, *, expected_identity):
        registrations.append((path, expected_identity))
        return {"url": f"http://127.0.0.1/resources/{len(registrations)}"}

    app = SimpleNamespace(service=SimpleNamespace(_results=lambda: store), server=SimpleNamespace(register=register))

    def view(*ids):
        query = {"case_id": ids[0]} if len(ids) == 1 else {"case_ids": list(ids)}
        return DesktopApplication.report_igv(app, {"run_id": "example", **query})
    return run, bams, store, view, registrations


def test_batch_uses_only_correct_caller_bam_and_site_and_verifies_reference_once(tmp_path, monkeypatch):
    run, bams, store, view, registrations = sources(tmp_path)
    tables = []
    for n, name in enumerate(("Father", "Mother"), 1):
        relative = f"output/individual_outputs/full_output_sample_{n:04d}.txt"
        table(run / relative, ["chr", "pos1", "pos2", "GT", "total_count"],
              [["1", 1, 2, "NA", 0], ["1", 3, 4, "0/0", 40], ["1", n, n + 1, "0/1", 21]])
        tables.append(artifact(run, relative, sample=name))
    validation(run, "dnp-call", {"dnp-tables": tables})
    first, second = report_cases(store, "example")
    from newpat.desktop import references
    checked = []
    original = references.indexed_reference_identity

    def observed(*args, **kwargs):
        checked.append(args[0])
        return original(*args, **kwargs)
    monkeypatch.setattr(references, "indexed_reference_identity", observed)
    result = view(first["id"], second["id"])["views"]
    for case_id, name, site in [(first["id"], "Father", "1:1-2"), (second["id"], "Mother", "1:2-3")]:
        prepared = result[case_id]
        assert prepared["available"] and prepared["site"] == site and prepared["locus"] == "1:1-4"
        assert prepared["marker"] == "DNP" and prepared["samples"] == [name]
        assert "Data row 3" in prepared["selection_note"] and "alternate allele" in prepared["selection_note"]
        assert [track["name"] for track in prepared["tracks"]] == [name]
        assert str(tmp_path) not in json.dumps(prepared)
    assert len(checked) == 1
    assert {p for p, stamp in registrations if p.suffix == ".bam" and stamp["mtime_ns"]} == {bams["Mother"], bams["Father"]}

    # A moved, edited or missing BAM can leave the verified archived coordinate usable.
    bams["Father"].write_bytes(b"changed")
    degraded = view(first["id"])
    assert not degraded["available"] and degraded["site"] == "1:1-2" and "tracks" not in degraded
    table(run / tables[1]["path"], ["chr", "pos1", "pos2", "GT", "total_count"], [["1", 3, 4, "0/1", 21]])
    degraded = view(second["id"])
    assert not degraded["available"] and "site" not in degraded


def test_postnatal_trio_excludes_unrelated_sample_and_noncontributing_coordinates(tmp_path):
    run, _bams, store, view, _ = sources(tmp_path, "cpin", "SNP")
    fields = ["Trio", "Marker_type", "CPI", "Log10_CPI", "N_sites", "Matching_sites", "Mismatching_sites",
              "Mismatch_probability"]
    summary = run / "output/Summary_Postnatal_CPI.txt"
    table(summary, fields, [["family", "SNP", 0.002, -2.6989700043, 2, 1, 1, 0.001]])
    relative = "output/family_sites.txt"
    table(run / relative, ["chr", "pos", "Status", "Paternity_Index", "Paternity_status"],
          [["1", 1, "missing_population_frequency", "NA", "NA"], ["1", 2, "eligible", 2, "match"],
           ["1", 3, "eligible", 0.001, "mismatch"]])
    family = {"trio": "one", "native_trio": "family", "sites": artifact(run, relative),
              **{r.lower(): {"sample": r} for r in ("Mother", "Father", "Child")}}
    validation(run, "cpin", {"cpin-trios": [family]})
    (case,) = report_cases(store, "example")
    selected = view(case["id"])
    assert selected["available"] and selected["site"] == "1:3-3"
    assert "paternal mismatch" in selected["selection_note"]
    assert selected["samples"] == ["Mother", "Father", "Child"]
    assert [s["name"] for s in selected["tracks"]] == selected["samples"]
    family["child"] = {"sample": "LostChild"}
    validation(run, "cpin", {"cpin-trios": [family]})
    (case,) = report_cases(store, "example")
    partial = view(case["id"])
    assert not partial["available"] and partial["site"] == "1:3-3" and "tracks" not in partial
    table(summary, [*fields, "Analysis"], [["family", "SNP", 2, 0.301, 1, 1, 0, 0.001, "heterozygous_child_sites"]])
    (case,) = report_cases(store, "example")
    assert "site" not in view(case["id"])


@pytest.mark.parametrize(("chrom", "expected"), [("X", False), ("chr1", True)])
def test_contamination_checks_the_exact_bam_contig_and_keeps_informative_zero(tmp_path, chrom, expected):
    run, _bams, store, view, _ = sources(tmp_path, "contamination", "SNP")
    table(run / "output/contamination_summary.txt", ["individuo", "informative_sites", "mean_contamination"],
          [["tested", 1, 0]])
    relative = "output/contamination_tested.txt"
    table(run / relative, ["chr", "pos", "contamination"], [[chrom, 1, "NA"], [chrom, 2, 0]])
    validation(run, "contamination", {"tables": [artifact(run, relative, sample="Child", native_name="tested")]})
    (case,) = report_cases(store, "example")
    selected = view(case["id"])
    assert selected["available"] is expected
    assert selected["site"] == f"{chrom}:2-2"
    if expected:
        assert selected["samples"] == ["Child"] and selected["reference_site"] == "1:2-2"
    assert "site" not in view("f" * 64)


def test_prenatal_iterations_are_never_used_as_coordinates(tmp_path):
    run, _bams, store, view, registered = sources(tmp_path, "cpi", "DNP")
    table(run / "output/Summary_FetalFraction_CPI.csv",
          ["Pair", "Cutoff", "CPI_medianFF", "N_sites_mother", "N_sites_father"], [["family", "panel", 1, 2, 3]])
    relative = "output/curves/family_panel_1.tsv"
    table(run / relative, ["Iteration", "log_CPI"], [[1, 1]])
    validation(run, "cpi", {"cpi-pairs": [{"pair": "one", "native_pair": "family",
                                         "curves": [artifact(run, relative, cutoff="panel")]}]})
    (case,) = report_cases(store, "example")
    assert "site" not in view(case["id"]) and not registered


def test_prenatal_hom_igv_reads_the_selected_panel_and_both_parental_tracks(tmp_path):
    run, _, store, view, _ = sources(tmp_path, "cpi", "SNP")
    table(run / "output/Summary_FetalFraction_CPI.csv", ["Pair", "Cutoff", "CPI_medianFF", "N_sites_mother", "N_sites_father",
          "Include_homozygous_child", "N_sites_HET_child", "N_sites_HOM_child"],
          [["pair", label, 1, 1, 1, "TRUE", 1, 1] for label in ("A", "B")])
    curves = []
    for i, label in enumerate(("A", "B"), 1):
        sites = f"output/pair_panel_{i}_HOM_child_sites.txt"
        curve = f"output/curves/pair_panel_{i}.tsv"
        table(run / sites, ["chr", "pos", "Paternity_Index", "Mismatch"], [["1", i, 0.25, "TRUE"]])
        table(run / curve, ["Iteration", "log_CPI"], [[1, 1]])
        curves.append(artifact(run, curve, cutoff=label, hom_sites=artifact(run, sites)))
    validation(run, "cpi", {"cpi-pairs": [{"pair": "parents", "native_pair": "pair", "curves": curves,
                "mother": {"sample": "Mother"}, "father": {"sample": "Father"}}]})
    a, b = report_cases(store, "example")
    results = view(a["id"], b["id"])["views"]
    for i, case in enumerate((a, b), 1):
        result = results[case["id"]]
        assert result["available"] and result["site"] == f"1:{i}-{i}"
        assert result["samples"] == ["Mother", "Father"]
        assert "among included HOM sites" in result["selection_note"]
