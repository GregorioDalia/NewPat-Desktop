"""Native R edge regressions; stdlib-only so the packaged image can run them.

Set NEWPAT_NATIVE_TEST_PAYLOAD_ROOT=/opt/newpat to exercise installed sources and
helpers. Without this override the current checkout is tested. Fixtures always
come from this checkout, never from a mounted replacement of the payload.
"""

import csv
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from newpat_scientific.errors import PlanExecutionError
from newpat_scientific.outputs import validate_standalone_outputs

from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = Path(os.environ.get("NEWPAT_NATIVE_TEST_PAYLOAD_ROOT", ROOT))
HELPERS = PAYLOAD / ("lib" if "NEWPAT_NATIVE_TEST_PAYLOAD_ROOT" in os.environ else "src") / "newpat_scientific"


def table(path, delimiter="\t"):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter=delimiter))


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class NativeREdgeCases(unittest.TestCase):
    def run_native(self, root, workflow, inputs, native_options=(), settings=None):
        output = root / "output"
        source = {"cpin": "CPI_postnatal/Postnatal_CPI.R",
                  "cpi": "CPI_from_cffDNA/cfDNA_CPI_estimator.R"}[workflow]
        arguments = ["Rscript", str(PAYLOAD / "scientific/vendor/NEWPAT" / source),
                     "--pileup_dir", str(inputs), "--out_dir", str(output),
                     "--mother_prefix", "Mother", "--father_prefix", "Father",
                     "--popfreq", str(inputs / "population.txt")]
        arguments += (["--trios", "M1:F1:C1", "--child_prefix", "Child"] if workflow == "cpin"
                      else ["--pairs", "M1:F1"])
        arguments.extend(native_options)
        env = dict(os.environ, NEWPAT_EXECUTION_MODE="serial",
                   NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                   NEWPAT_SETTINGS_HELPER=str(HELPERS / "settings.R"),
                   NEWPAT_SETTINGS_REGISTRY=str(HELPERS / "settings_data.json"),
                   NEWPAT_PLOTS_HELPER=str(HELPERS / "plots.R"))
        env.pop("NEWPAT_SCIENTIFIC_SETTINGS", None)
        if settings is not None:
            settings_path = root / "scientific-settings-request.json"
            settings_path.write_text(json.dumps({"schema_version": 1, "workflow": workflow,
                                                 "parameters": settings}))
            env["NEWPAT_SCIENTIFIC_SETTINGS"] = str(settings_path)
        process = subprocess.run(arguments, cwd=root, env=env, capture_output=True, text=True, timeout=90)
        return process, output

    def test_cpin_absent_and_uncovered_samples(self):
        for marker in ("SNP", "DNP"):
            for case in ("empty_child", "empty_trio", "uncovered_child"):
                with self.subTest(marker=marker, case=case), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    inputs = root / "inputs"
                    shutil.copytree(ROOT / "tests/fixtures/cpin" / marker, inputs)
                    samples = ("MotherM1", "FatherF1", "ChildC1") if case == "empty_trio" else ("ChildC1",)
                    for sample in samples:
                        path = inputs / f"{sample}.txt"
                        rows = table(path)
                        with path.open("w", newline="") as stream:
                            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
                            writer.writeheader()
                            if case == "uncovered_child":
                                for row in rows:
                                    row.update(N_REF="0", N_ALT="0", N_Other="0", total_count="NA")
                                writer.writerows(rows)
                    process, output = self.run_native(root, "cpin", inputs)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    summaries = table(output / "Summary_Postnatal_CPI.txt")
                    self.assertEqual(len(summaries), 1)
                    for row in summaries:
                        self.assertEqual((row["N_sites"], row["CPI"], row["Log10_CPI"]), ("0", "NA", "NA"))
                    sites = table(next(output.glob("*_sites.txt")))
                    expected = "quality_filter" if case == "uncovered_child" else "missing_call"
                    self.assertEqual({row["Status"] for row in sites}, {expected} if case != "empty_trio" else set())
                    self.assertFalse((output / "curves").exists())

    def test_cpi_empty_and_uncovered_samples_preserve_invalid_total_errors(self):
        for marker in ("SNP", "DNP"):
            for case in ("empty", "uncovered", "malformed"):
                with self.subTest(marker=marker, case=case), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    inputs = root / "inputs"
                    shutil.copytree(ROOT / "tests/fixtures/cpin" / marker, inputs)
                    for sample in ("MotherM1", "FatherF1"):
                        path = inputs / f"{sample}.txt"
                        rows = table(path)
                        with path.open("w", newline="") as stream:
                            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
                            writer.writeheader()
                            if case != "empty":
                                for row in rows:
                                    row.update(N_REF="0", N_ALT="0", N_Other="0",
                                               total_count="NA" if case == "uncovered" else "bad")
                                writer.writerows(rows)
                    process, output = self.run_native(root, "cpi", inputs)
                    if case == "malformed":
                        self.assertNotEqual(process.returncode, 0)
                        self.assertIn("invalid total_count", process.stderr)
                        self.assertFalse((output / "Summary_FetalFraction_CPI.csv").exists())
                    else:
                        self.assertEqual(process.returncode, 0, process.stderr)
                        summaries = table(output / "Summary_FetalFraction_CPI.csv", ",")
                        self.assertEqual(len(summaries), 1)
                        self.assertEqual(summaries[0]["N_sites_mother"], "0")
                        self.assertEqual(summaries[0]["N_sites_father"], "0")
                        self.assertEqual(summaries[0]["Mean_logCPI"], "NA")

    def test_prenatal_exclusions_and_curve_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            header = "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
            (inputs / "MotherM1.txt").write_text(header + "".join(
                f"1\t{i}\tA\tG\t{100-alt}\t{alt}\t0\t100\n" for i, alt in enumerate((2, 3, 5), 1)))
            (inputs / "FatherF1.txt").write_text(header + "".join(
                f"1\t{i}\tA\tG\t{ref}\t{100-ref}\t0\t100\n" for i, ref in enumerate((0, 80, 0), 1)))
            (inputs / "population.txt").write_text(
                "chr\tpos\tRef_f.pop\tAlt_f.pop\n1\t1\t0.8\t0.2\n1\t2\t0.6\t0.4\n")
            process, output = self.run_native(root, "cpi", inputs)
            self.assertEqual(process.returncode, 0, process.stderr)
            request = {"workflow": "cpi", "marker_type": "SNP", "pairs": "M1:F1", "cutoffs": [],
                       "cutoff_mode": "all", "work_dir": str(root / "work"), "out_dir": str(output)}
            artifacts = validate_standalone_outputs(request)
            self.assertEqual({w["code"] for w in artifacts["quality_warnings"]},
                             {"output.cpi_missing_frequency", "output.cpi_unassigned_father"})
            support = artifacts["cpi-pairs"][0]["curves"][0]["prenatal_support"]
            self.assertEqual(support, {"minimum_fetal_reads": 2, "paternal_candidates": 3, "paternal_used": 1,
                                       "missing_frequency": 1, "unassigned_father": 1,
                                       "median_fetal_reads": 3, "paternal_used_at_median": 0})
            summary = table(output / "Summary_FetalFraction_CPI.csv", ",")[0]
            self.assertEqual((summary["N_sites_father"], summary["Max_logCPI"], summary["CPI_medianFF"]),
                             ("3", "0.699", "NA"))
            curve = next((output / "curves").glob("*.tsv"))
            lines = curve.read_text().splitlines(keepends=True)
            for damaged in (lines[:1], lines[:1] + lines[2:], lines[:2] + lines[1:],
                            [line.replace("0.698970004336019", "text") for line in lines]):
                curve.write_text("".join(damaged))
                with self.assertRaises(PlanExecutionError):
                    validate_standalone_outputs(request)

    def test_cpi_log_stays_finite_outside_the_raw_product_range(self):
        for loci, father, expected in ((400, (0, 100), 400.0),
                                       (200, (100, 0), 200 * math.log10(0.002))):
            with self.subTest(loci=loci), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs = root / "inputs"
                inputs.mkdir()
                header = "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
                (inputs / "MotherM1.txt").write_text(header + "".join(
                    f"01\t{i}\tA\tG\t95\t5\t0\t100\n" for i in range(2, loci + 2)))
                (inputs / "FatherF1.txt").write_text(header + "".join(
                    f"01\t{i}\tA\tG\t{father[0]}\t{father[1]}\t0\t100\n" for i in range(2, loci + 2)))
                alt = 0.1 if loci == 400 else 0.5
                (inputs / "population.txt").write_text("chr\tpos\tRef_f.pop\tAlt_f.pop\n" + "".join(
                    f"01\t{i}\t{1-alt}\t{alt}\n" for i in range(2, loci + 2)))
                process, output = self.run_native(root, "cpi", inputs)
                self.assertEqual(process.returncode, 0, process.stderr)
                rows = table(next((output / "curves").glob("*.tsv")))
                self.assertTrue(rows)
                for row in rows:
                    self.assertAlmostEqual(float(row["log_CPI"]), expected, places=8)
                    self.assertEqual(float(row["CPI"]), math.inf if loci == 400 else 0.0)
                summary = table(output / "Summary_FetalFraction_CPI.csv", ",")[0]
                self.assertAlmostEqual(float(summary["CPI_medianFF"]), expected, places=3)
                request = {"workflow": "cpi", "marker_type": "SNP", "pairs": "M1:F1", "cutoffs": [],
                           "cutoff_mode": "all", "work_dir": str(root / "work"), "out_dir": str(output)}
                self.assertEqual(validate_standalone_outputs(request)["quality_warnings"], [])
                # Raw Inf/zero is legitimate here, but the reported log must agree with the curve.
                summary_path = output / "Summary_FetalFraction_CPI.csv"
                summary["CPI_medianFF"] = str(float(summary["CPI_medianFF"]) + 0.01)
                with summary_path.open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=summary)
                    writer.writeheader()
                    writer.writerow(summary)
                with self.assertRaisesRegex(PlanExecutionError, "median-threshold"):
                    validate_standalone_outputs(request)

    def test_downstream_joins_preserve_numeric_looking_contigs(self):
        for workflow in ("cpi", "cpin"):
            with self.subTest(workflow=workflow), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs = root / "inputs"
                inputs.mkdir()
                header = "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
                (inputs / "MotherM1.txt").write_text(header + "01\t20\tA\tG\t95\t5\t0\t100\n")
                (inputs / "FatherF1.txt").write_text(header + "1\t20\tA\tG\t0\t100\t0\t100\n")
                (inputs / "ChildC1.txt").write_text(header + "01\t20\tA\tG\t50\t50\t0\t100\n")
                (inputs / "population.txt").write_text("chr\tpos\tRef_f.pop\tAlt_f.pop\n01\t20\t0.8\t0.2\n")
                process, output = self.run_native(root, workflow, inputs)
                self.assertEqual(process.returncode, 0, process.stderr)
                if workflow == "cpi":
                    row = table(output / "Summary_FetalFraction_CPI.csv", ",")[0]
                    self.assertEqual((row["N_sites_father"], row["CPI_medianFF"]), ("0", "NA"))
                else:
                    rows = table(output / "Summary_Postnatal_CPI.txt")
                    self.assertTrue(all(row["N_sites"] == "0" and row["Log10_CPI"] == "NA" for row in rows))

    def test_cpin_tiny_positive_frequencies_preserve_finite_log_cpi(self):
        for marker in ("SNP", "DNP"):
            for frequency in ("1e-310", "0"):
                with self.subTest(marker=marker, frequency=frequency), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    inputs = root / "inputs"
                    shutil.copytree(ROOT / "tests/fixtures/cpin" / marker, inputs)
                    population = inputs / "population.txt"
                    rows = table(population)
                    for row in rows:
                        row.update({"Ref_f.pop": frequency, "Alt_f.pop": frequency})
                    with population.open("w", newline="") as stream:
                        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
                        writer.writeheader()
                        writer.writerows(rows)
                    process, output = self.run_native(root, "cpin", inputs)
                    if frequency == "0":
                        self.assertNotEqual(process.returncode, 0)
                        self.assertIn("finite and in (0, 1]", process.stderr)
                        self.assertFalse((output / "Summary_Postnatal_CPI.txt").exists())
                    else:
                        self.assertEqual(process.returncode, 0, process.stderr)
                        summaries = table(output / "Summary_Postnatal_CPI.txt")
                        self.assertEqual([row["N_sites"] for row in summaries], ["5"])
                        for row in summaries:
                            # Two mismatches, one heterozygous father, one matching
                            # homozygous father and one het/het PI = 1/(2*f).
                            expected = 2 * math.log10(0.5) + 2 * math.log10(float(row["Mismatch_probability"]))
                            expected -= int(row["N_sites"]) * math.log10(float(frequency))
                            self.assertAlmostEqual(float(row["Log10_CPI"]), expected, places=10)
                        # A per-site PI may also overflow. The desktop artifact validator
                        # must still accept the finite logarithm of the complete product.
                        request = {"workflow": "cpin", "marker_type": marker, "trios": "M1:F1:C1",
                                   "work_dir": str(root / "work"), "out_dir": str(output)}
                        result = validate_standalone_outputs(request)
                        self.assertEqual(len(result["cpin-trios"]), 1)


if __name__ == "__main__":
    unittest.main()
