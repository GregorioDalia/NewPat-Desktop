"""Check the installed fetal-sex program against published tables and hand-worked cases."""

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from native_engine_helpers import execute_workflow
from test_native_r_edge_cases import HELPERS, PAYLOAD, ROOT


FIXTURE = ROOT / "tests/fixtures/fetal_sex"
PROGRAM = PAYLOAD / "scientific/vendor/NEWPAT/Fetal_sex/Fetal_sex.R"


def example(sample):
    return {key: str(FIXTURE / "inputs" / f"{sample}_{suffix}.txt")
            for key, suffix in (("autosomes", "autosomes"), ("x", "X"), ("y", "Y"))}


def combined_example(sample, root):
    inputs = example(sample)
    autosomes = Path(inputs["autosomes"])
    header, *a_rows = autosomes.read_text(encoding="utf-8").splitlines()
    _, *x_rows = Path(inputs["x"]).read_text(encoding="utf-8").splitlines()
    path = root / autosomes.name
    path.write_text("\n".join([header, *x_rows[:1], *a_rows, *x_rows[1:]]) + "\n", encoding="utf-8")
    return {"dnp": str(path), "y": inputs["y"]}


class NativeFetalSex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        r = shutil.which("Rscript")
        if r and subprocess.run(
            [r, "--vanilla", "-e", 'stopifnot(requireNamespace("optparse"), requireNamespace("dplyr"))'],
            capture_output=True, timeout=45,
        ).returncode == 0:
            return
        message = "R with optparse and dplyr is required for fetal-sex regressions"
        if "NIPAT_NATIVE_TEST_PAYLOAD_ROOT" in os.environ:
            raise RuntimeError(message)
        raise unittest.SkipTest(message)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def invoke(self, name, inputs, *options):
        out = self.root / name
        result = subprocess.run(
            ["Rscript", "--vanilla", str(PROGRAM), "--autosomes", inputs["autosomes"],
             "--X", inputs["x"], "--Y", inputs["y"], "--out", str(out), *options],
            capture_output=True, text=True, timeout=60,
        )
        return result, out

    def summary(self, name, inputs, *options):
        result, out = self.invoke(name, inputs, *options)
        self.assertEqual(result.returncode, 0, result.stderr)
        with (out / "Fetal_sex_summary.txt").open(encoding="utf-8") as stream:
            row, = csv.DictReader(stream, delimiter="\t")
        return row

    def test_engine_matches_published_tables_for_both_samples(self):
        for sample in ("Female_fetus", "Male_fetus"):
            with self.subTest(sample=sample):
                run = self.root / sample
                result = execute_workflow("fetal-sex", run, **example(sample))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                expected = sorted((FIXTURE / "outputs" / sample).glob("*.txt"))
                self.assertEqual(len(expected), 4)
                for source in expected:
                    actual = run / "output" / source.name
                    self.assertEqual(actual.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"),
                                     source.name)

    def test_combined_dnp_matches_all_four_reference_tables_and_indeterminate_case(self):
        for sample in ("Female_fetus", "Male_fetus"):
            with self.subTest(sample=sample):
                combined = combined_example(sample, self.root)
                run = self.root / (sample + "-combined")
                result = execute_workflow("fetal-sex", run, **combined)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                for source in (FIXTURE / "outputs" / sample).glob("*.txt"):
                    self.assertEqual((run / "output" / source.name).read_text(encoding="utf-8"),
                                     source.read_text(encoding="utf-8"), source.name)
        settings = {"a_threshold": 0.125}
        for name, inputs in (("split", example("Male_fetus")), ("combined", combined_example("Male_fetus", self.root))):
            run = self.root / name
            result = execute_workflow("fetal-sex", run, **inputs, scientific_settings=settings)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        baseline = self.root / "split/output"
        with (baseline / "Fetal_sex_summary.txt").open() as stream:
            row, = csv.DictReader(stream, delimiter="\t")
        self.assertEqual(row["Fetal_sex"], "Undetermined")
        for source in baseline.glob("*.txt"):
            self.assertEqual((self.root / "combined/output" / source.name).read_bytes(), source.read_bytes())

    def test_shared_maternal_dnp_feeds_contamination_and_fetal_sex(self):
        for layout in ("split", "combined"):
            with self.subTest(layout=layout):
                self.check_shared_maternal_dnp(layout)

    def check_shared_maternal_dnp(self, layout):
        inputs = (combined_example("Female_fetus", self.root) if layout == "combined"
                  else example("Female_fetus"))
        maternal = "dnp_Maternal"
        panel = self.root / "panel.tsv"
        panel.write_text("chr\tpos1\tpos2\nchr1\t3010000\t3010001\nchr1\t3020000\t3020001\n",
                         encoding="utf-8")
        role_ids = {"autosomes": maternal, "x": "fsx_Maternal", "y": "fsy_Maternal"}
        if layout == "combined":
            role_ids = {"dnp": maternal, "y": "fsy_Maternal"}
        plan = {"schema_version": 1,
                "samples": [{"id": identifier, "kind": "snp-table" if role == "y" else "dnp-table",
                             "path": inputs[role]} for role, identifier in role_ids.items()],
                "steps": [{"id": "contamination", "workflow": "contamination",
                           "inputs": {"samples": [{"sample": maternal}], "panel": str(panel)}, "parameters": {}},
                          {"id": "sex", "workflow": "fetal-sex", "inputs": role_ids, "parameters": {}}]}
        manifest = self.root / "plan.json"
        manifest.write_text(json.dumps(plan), encoding="utf-8")
        run = self.root / layout
        result = subprocess.run(
            [sys.executable, str(PAYLOAD / "engine/main.py"), "execute-plan",
             "--plan", str(manifest), "--run-dir", str(run)],
            env=dict(os.environ, NIPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R")),
            capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        state = json.loads((run / "workflow-state.json").read_text(encoding="utf-8"))
        self.assertEqual([step["status"] for step in state["steps"]], ["succeeded", "succeeded"])
        sex = run / "steps/sex/output"
        expected = sorted((FIXTURE / "outputs/Female_fetus").glob("*.txt"))
        self.assertEqual(len(expected), 4)
        for source in expected:
            self.assertEqual((sex / source.name).read_text(encoding="utf-8"),
                             source.read_text(encoding="utf-8"), source.name)
        with (run / "steps/contamination/output/contamination_summary.txt").open(encoding="utf-8") as stream:
            row, = csv.DictReader(stream, delimiter="\t")
        self.assertEqual(row["informative_sites"], "2")
        self.assertAlmostEqual(float(row["mean_contamination"]), 0.02)

    def test_classification_uses_all_three_exact_boundaries(self):
        # Published male input gives A=1/8, B=3/2 and C=12. A equality is
        # female-inclusive, male-exclusive; the B and C comparisons include equality.
        inputs = example("Male_fetus")
        cases = (
            ("M", ("--B_male_min", "1.5", "--C_male_min", "12")),
            ("Undetermined", ("--A_threshold", "0.125")),
            ("Undetermined", ("--C_male_min", "12.01")),
            ("F", ("--A_threshold", "0.125", "--B_female_max", "1.5", "--B_male_min", "2",
                   "--C_female_max", "12", "--C_male_min", "13")),
        )
        for idx, (expected, options) in enumerate(cases):
            with self.subTest(expected=expected, options=options):
                row = self.summary(f"threshold-{idx}", inputs, *options)
                self.assertEqual(row["Fetal_sex"], expected)
                self.assertEqual([row[f"Ratio_{key}"] for key in "ABC"], ["0.125", "1.5", "12"])

    def test_read_and_percent_filters_apply_independently_or_together(self):
        inputs = example("Male_fetus")
        x = self.root / "thresholds-X.txt"
        x.write_text(
            "chr\tpos1\tpos2\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
            "chrX\t11\t12\tAA\tCC\t99\t1\t0\t100\n"
            "chrX\t21\t22\tAA\tCC\t998\t2\t0\t1000\n"
            "chrX\t31\t32\tAA\tCC\t97\t3\t0\t100\n", encoding="utf-8")
        inputs["x"] = str(x)
        cases = (
            ((), "2", "5", "2", "NA"),
            (("--min_fetal_percent", "1"), "2", "4", "NA", "1"),
            (("--min_fetal_reads", "2", "--min_fetal_percent", "1"), "1", "3", "2", "1"),
            (("--min_fetal_reads", "4"), "0", "0", "4", "NA"),
        )
        for idx, (options, sites, reads, minimum, percent) in enumerate(cases):
            with self.subTest(options=options):
                row = self.summary(f"filter-{idx}", inputs, *options)
                self.assertEqual([row[key] for key in ("N_X_sites", "Fetal_reads_X", "Min_fetal_reads",
                                                      "Min_fetal_percent")], [sites, reads, minimum, percent])
                if sites == "0":
                    self.assertEqual([row[key] for key in ("MFF_X", "Ratio_A", "Ratio_C", "Fetal_sex")],
                                     ["NA", "NA", "NA", "Undetermined"])

    def test_effect_of_uncovered_y_markers(self):
        inputs = example("Female_fetus")
        row = self.summary("no-covered", inputs, "--include_zero_coverage_Y", "FALSE")
        self.assertEqual([row[key] for key in ("N_Y_sites_used", "MFF_Y", "Fetal_sex")], ["0", "0", "F"])
        y = self.root / "mixed-Y.txt"
        y.write_text("chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
                     "Y\t10\tA\tG\t0\t0\t0\t0\nY\t20\tA\tG\t3\t1\t0\t4\n", encoding="utf-8")
        inputs["y"] = str(y)
        for flag, used, mean, outcome in (("TRUE", "2", "2", "F"), ("FALSE", "1", "4", "Undetermined")):
            with self.subTest(flag=flag):
                row = self.summary(flag, inputs, "--include_zero_coverage_Y", flag)
                self.assertEqual([row[key] for key in ("N_Y_covered_sites", "N_Y_sites_used", "MFF_Y", "Fetal_sex")],
                                 ["1", used, mean, outcome])

    def test_rejects_wrong_chromosomes_and_inconsistent_thresholds(self):
        inputs = example("Male_fetus")
        for name, source, options, reason in (
            ("swapped", dict(inputs, x=inputs["autosomes"]), (), "Non-X markers"),
            ("ranges", inputs, ("--B_female_max", "1"), "Invalid fetal sex classification thresholds"),
        ):
            with self.subTest(name=name):
                result, out = self.invoke(name, source, *options)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(reason, result.stderr)
                self.assertFalse(out.exists())
