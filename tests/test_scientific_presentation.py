"""Readable artifacts preserve canonical scientific identity and values."""

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from nipat_scientific.errors import ValidationError
from nipat_scientific.plan import validate_plan
from nipat_scientific.presentation import (
    _copy_table, _filename, _interpretation_notes, _unique_labels, finish_plan_presentation, finish_presentation,
    normalize_presentation, prepare_presentation, step_presentation,
    validate_request_presentation,
)


class PresentationTests(unittest.TestCase):
    def test_exact_coverage_and_labels_are_data(self):
        labels = {"a": 'È un campione "A".bam', "b": "sample_0001.bam"}
        self.assertEqual(normalize_presentation({"samples": labels, "pairs": {}}, set(labels))["samples"], labels)
        for value in ({"a": "a.bam"}, {"a": "a.bam", "b": "b.bam", "c": "c.bam"}):
            with self.assertRaises(ValidationError):
                normalize_presentation({"samples": value, "pairs": {}}, {"a", "b"})
        for name in ("../escape", "a\\b", "a\tb", "a\nb", "a\x00b", "a\u202eb", ""):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                normalize_presentation({"samples": {"a": name}, "pairs": {}}, {"a"})

    def test_duplicate_names_are_distinct_and_portable(self):
        names = {"one": "é.bam", "two": "e\u0301.bam", "three": "É.bam"}
        labels = _unique_labels(names)
        self.assertEqual(labels, _unique_labels(dict(reversed(list(names.items())))))
        self.assertEqual(len(set(labels.values())), 3)
        for identity, original in names.items():
            self.assertIn(original, labels[identity])
            self.assertIn(identity, labels[identity])
        first, second = _filename("con: ?" + "界" * 600, "one"), _filename("con: ?" + "界" * 600, "two")
        self.assertNotEqual(first.casefold(), second.casefold())
        self.assertLess(len(first.encode()), 195)
        self.assertFalse(any(char in first for char in '/\\:*?"<>|'))

    def test_tables_replace_identity_only_and_keep_numeric_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "native.csv", Path(tmp) / "readable.csv"
            content = 'Pair,GT_sample_0001,N_REF,CPI_medianFF,other\n"pair",0/1,001,6.020000e-1,sample_0001\n'
            source.write_text(content, encoding="utf-8")
            _copy_table(source, target, {"pair": 'Madre: "A" | Padre: B', "GT_sample_0001": "GT_Campione à.bam", "sample_0001": "A.bam"})
            with target.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["Pair", "GT_Campione à.bam", "N_REF", "CPI_medianFF", "other"])
            self.assertEqual(rows[1], ['Madre: "A" | Padre: B', "0/1", "001", "6.020000e-1", "sample_0001"])
            self.assertEqual(source.read_text(encoding="utf-8"), content)

    def test_legacy_command_unchanged(self):
        request = {"workflow": "snp-call"}
        self.assertIsNone(validate_request_presentation(request))
        script = Path("/native.R")
        self.assertEqual(prepare_presentation(request, script, ["--a", "b"]), ["Rscript", str(script), "--a", "b"])

    def test_spreadsheet_labels_are_text_but_negative_numbers_stay_numeric(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "native.txt", Path(tmp) / "readable.txt"
            source.write_text("individuo\tGL0\nA\t-1.230\n", encoding="utf-8")
            _copy_table(source, target, {"A": ' =1+2&".bam"'})
            with target.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle, delimiter="\t"))
            self.assertEqual(rows[1], ['\' =1+2&".bam"', "-1.230"])

    def test_snp_export_is_readable_escaped_and_canonical_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, output = root / "work", root / "output"
            work.mkdir(); output.mkdir()
            request = {"workflow": "snp-call", "work_dir": str(work), "out_dir": str(output),
                       "presentation": {"samples": {"sample_0001": "<script>alert(1)<.pileup"}, "pairs": {}}}
            command = prepare_presentation(request, Path("/native.R"), ["one", "two"])
            self.assertTrue(command[1].endswith("presentation.R"))
            self.assertEqual(command[2:], ["one", "two"])
            native = output / "SNPcall_output.txt"
            native.write_text("pos\tN_REF\n1\t010\n", encoding="utf-8")
            before = native.read_bytes()
            config = json.loads((work / "presentation-config.json").read_text(encoding="utf-8"))
            self.assertEqual(len(config["plots"]), 5)
            self.assertEqual(len(config["tables"]), 3)
            for source, entry in config["tables"].items():
                path = output / source
                if path == native:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("sample\tseconds\n sample_0001\t1.25\n" if source.endswith("resources.tsv")
                                else "chr\tpos\tGT_sample_0001\n1\t1\tNA\n", encoding="utf-8")
            for source, entry in config["plots"].items():
                path = output / source
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"%PDF-native")
                (output / "presentation" / entry["target"]).write_bytes(b"%PDF-readable")
            report = finish_presentation(request, root)
            self.assertEqual(report["status"], "complete")
            index = (root / report["index"]["path"]).read_text(encoding="utf-8")
            self.assertIn("<title>Risultati NewPat</title>", index)
            self.assertIn("<h1>SNPcall</h1>", index)
            self.assertIn("&lt;script&gt;", index)
            self.assertNotIn("<script>", index)
            self.assertEqual(native.read_bytes(), before)
            readable = root / report["files"][0]["path"]
            with readable.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle, delimiter="\t"))
            self.assertEqual(rows, [["Sample", "pos", "N_REF"], ["<script>alert(1)<.pileup", "1", "010"]])

    def test_postnatal_readable_tables_preserve_scalar_and_excluded_sites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work, output = root / "work", root / "output"
            work.mkdir()
            output.mkdir()
            names = {"MotherM": "Madre A.txt", "FatherF": "Padre B.txt", "ChildC": "Figlio C.txt"}
            request = {"workflow": "cpin", "work_dir": str(work), "out_dir": str(output),
                       "samples": [{"name": key + ".txt"} for key in names],
                       "trios": "M:F:C", "marker_type": "SNP",
                       "mother_prefix": "Mother", "father_prefix": "Father", "child_prefix": "Child",
                       "presentation": {"samples": names, "pairs": {"M:F:C": "Trio A"}}}
            prepare_presentation(request, Path("/native.R"), [])
            trio = "MotherM-FatherF-ChildC_SNPs"
            config = json.loads((work / "presentation-config.json").read_text(encoding="utf-8"))
            summary, sites = "Summary_Postnatal_CPI.txt", f"{trio}_sites.txt"
            self.assertEqual(set(config["tables"]), {summary, sites})
            self.assertEqual(config["plots"], {})
            (output / summary).write_text(f"Trio\tCPI\tLog10_CPI\n{trio}\tNA\tNA\n", encoding="utf-8")
            site_text = "pos\tStatus\tPaternity_Index\n15\tquality_filter\tNA\n"
            (output / sites).write_text(site_text, encoding="utf-8")
            report = finish_presentation(request, root)
            self.assertEqual([entry["kind"] for entry in report["files"]], ["table", "table"])
            displayed = output / "presentation"
            self.assertEqual((displayed / summary).read_text(encoding="utf-8").splitlines()[1], "Trio A\tNA\tNA")
            self.assertEqual((displayed / config["tables"][sites]["target"]).read_text(encoding="utf-8"), site_text)
            self.assertIn("un unico CPI per trio", (root / report["index"]["path"]).read_text(encoding="utf-8"))

    def test_bad_late_row_discards_only_the_export_created_by_this_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "source.tsv", Path(tmp) / "readable.tsv"
            source.write_text("chr\tpos\n1\t123\n2\n", encoding="utf-8")
            with self.assertRaisesRegex(ValidationError, "Tabella non rettangolare"):
                _copy_table(source, target, {}, sample="A")
            self.assertFalse(target.exists())
            target.write_text("previous result", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                _copy_table(source, target, {}, sample="A")
            self.assertEqual(target.read_text(encoding="utf-8"), "previous result")

    def test_resources_relabel_sample_without_changing_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "resources.tsv", Path(tmp) / "readable.tsv"
            source.write_text("sample\tseconds\tresident_MB_start\tresident_MB_end\n"
                              "sample_0001\t1.2300\t123.456\t100.000\n", encoding="utf-8")
            _copy_table(source, target, {"sample_0001": "Campione à.bam"})
            self.assertEqual(target.read_text(encoding="utf-8").splitlines()[1],
                             "Campione à.bam\t1.2300\t123.456\t100.000")

    def test_result_notes_distinguish_units_missingness_and_coverage(self):
        snp = _interpretation_notes("snp-call")
        self.assertIn("log-verosimiglianze naturali", snp)
        self.assertIn("N_REF / (N_REF + N_ALT)", snp)
        self.assertIn("non la sola presenza di copertura", snp)
        self.assertIn("non misurano il picco", snp)
        self.assertIn("CPI_medianFF", _interpretation_notes("cpi"))
        self.assertIn("0,025 corrisponde al 2,5%", _interpretation_notes("contamination"))
        for workflow in ("snp-call", "dnp-call", "cpi", "cpin", "contamination"):
            self.assertIn("non equivale a zero", _interpretation_notes(workflow))

    def test_missing_plot_fails_visibly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / "work").mkdir(); (root / "output").mkdir()
            request = {"workflow": "dnp-call", "samples": [{"sample_id": "sample_0001"}],
                       "work_dir": str(root / "work"), "out_dir": str(root / "output"),
                       "presentation": {"samples": {"sample_0001": "A.bam"}, "pairs": {}}}
            prepare_presentation(request, Path("/native.R"), [])
            config = json.loads((root / "work/presentation-config.json").read_text(encoding="utf-8"))
            for source in config["tables"]:
                target = root / "output" / source; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("chr\tGT_sample_0001\n1\t0/0\n", encoding="utf-8")
            for source in config["plots"]:
                target = root / "output" / source; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"%PDF-native")
            with self.assertRaisesRegex(ValidationError, "Esportazione assente"):
                finish_presentation(request, root)
            self.assertFalse((root / "work/presentation-report.json").exists())

    def test_plan_index_links_complete_snp_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "snp_summary/group_0001"
            folder.mkdir(parents=True)
            records = {}
            for key, name in (("genotypes", "merged_genotypes.tsv"), ("resources", "resources.tsv"),
                              ("sample_labels", "sample_labels.tsv"), ("plot", "Unassigned_genotypes.pdf")):
                path = folder / name
                path.write_text("synthetic", encoding="utf-8")
                records[key] = {"path": path.relative_to(root).as_posix()}
            group = {"id": "group_0001", "samples": ["a", "b"], "plots": [records.pop("plot")], **records}
            with patch("nipat_scientific.presentation.hashlib.file_digest", wraps=hashlib.file_digest) as digests:
                report = finish_plan_presentation({"presentation": {}},
                                                  {"status": "succeeded", "steps": [], "snp_summary": [group]}, root)
            self.assertEqual([Path(call.args[0].name) for call in digests.call_args_list],
                             [root / "presentation/index.html"])
            content = (root / report["index"]["path"]).read_text(encoding="utf-8")
            self.assertIn("2 campioni", content)
            self.assertIn("../snp_summary/group_0001/merged_genotypes.tsv", content)
            self.assertIn("non la sola copertura", content)

    def test_plan_index_rejects_missing_or_outside_summary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "outside.tsv").touch()
            for label, invalid in (("missing", "missing.tsv"), ("outside", "../outside.tsv")):
                with self.subTest(label=label):
                    root = directory / label
                    root.mkdir()
                    group = dict.fromkeys(("genotypes", "resources", "sample_labels"), {"path": invalid})
                    group.update(id="comparison", samples=["a", "b"], plots=[])
                    with self.assertRaisesRegex(ValidationError, "Esportazione assente"):
                        finish_plan_presentation({"presentation": {}},
                                                 {"status": "succeeded", "steps": [], "snp_summary": [group]}, root)
                    self.assertFalse((root / "presentation/index.html").exists())

    def test_reordered_plan_inputs_keep_identity_not_position(self):
        plan = {"presentation": {"samples": {"a": "A.bam", "b": "B.bam"}, "pairs": {}}}
        dnp = {"workflow": "dnp-call", "inputs": {"samples": ["b", "a"]}}
        contamination = {"workflow": "contamination", "inputs": {"samples": [{"sample": "b"}, {"sample": "a"}]}}
        self.assertEqual(step_presentation(plan, dnp, {})["samples"], {"sample_0001": "B.bam", "sample_0002": "A.bam"})
        self.assertEqual(step_presentation(plan, contamination, {})["samples"], {"table_0001": "B.bam", "table_0002": "A.bam"})
        bindings = [{"native_selection": "m001:f001", "pair": "family", "mother": {"sample": "b"}, "father": {"sample": "a"}}]
        cpi = step_presentation(plan, {"workflow": "cpi"}, {}, bindings)
        self.assertEqual(cpi["samples"], {"Motherm001": "B.bam", "Fatherf001": "A.bam"})
        self.assertEqual(cpi["pairs"]["m001:f001"], "family — Mother: B.bam | Father: A.bam")

    def test_plan_preserves_complete_presentation_and_rejects_unknown_identity(self):
        plan = {"schema_version": 1, "samples": [{"id": "sample_a", "kind": "bam", "path": "/inputs/a.bam"}],
                "steps": [{"id": "dnp", "workflow": "dnp-call", "inputs": {"samples": ["sample_a"],
                           "reference": "/inputs/ref.fa", "panel": "/inputs/panel.txt"}, "parameters": {"parallel": False}}],
                "presentation": {"samples": {"sample_a": "Original à.bam"}, "pairs": {}}}
        canonical = validate_plan(plan)["plan"]
        self.assertEqual(canonical["presentation"], plan["presentation"])
        plan["presentation"]["samples"] = {"wrong": "Original à.bam"}
        with self.assertRaisesRegex(ValidationError, "plan.presentation"):
            validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
