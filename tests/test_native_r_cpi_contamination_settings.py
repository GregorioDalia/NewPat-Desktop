"""Run native CPI and contamination regressions against the active scientific payload."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from nipat_scientific.settings import settings_context
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
from test_native_r_edge_cases import HELPERS, PAYLOAD, ROOT, table

FIXTURE = ROOT / "tests/fixtures/five_modules/SNP"
SCRIPTS = PAYLOAD / "scientific/vendor/NEWPAT"


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class NativeCPIContaminationSettings(unittest.TestCase):
    def execute(self, workflow, settings, flags=(), inputs=None):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        work, output = root / "work", root / "output"
        work.mkdir()
        with settings_context(workflow, settings, work):
            env = dict(os.environ, NIPAT_EXECUTION_MODE="serial",
                       NIPAT_SETTINGS_HELPER=str(HELPERS / "settings.R"),
                       NIPAT_SETTINGS_REGISTRY=str(HELPERS / "settings_data.json"),
                       NIPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                       NIPAT_PLOTS_HELPER=str(HELPERS / "plots.R"))
            if workflow == "cpi":
                arguments = [SCRIPTS / "CPI_from_cffDNA/cfDNA_CPI_estimator.R",
                             "--pileup_dir", inputs or FIXTURE / "cpi", "--out_dir", output,
                             "--pairs=M:F", "--mother_prefix=Mother", "--father_prefix=Father",
                             "--popfreq", FIXTURE / "cpi/population.tsv"]
            else:
                arguments = [SCRIPTS / "contamination/detect_contamination.R",
                             FIXTURE / "contamination/panel.tsv", FIXTURE / "contamination/Calls.txt", output]
            result = subprocess.run(["Rscript", *arguments, *flags], env=env, capture_output=True,
                                    text=True, timeout=90)
        return result, output

    def test_cpi_explicit_overrides_are_recorded_after_config(self):
        result, output = self.execute("cpi", {"err_const_snp": 0.02, "min_fetal_reads": 5},
                                      ["--err_const_snp", "0.04", "--err_const", "0.06",
                                       "--err_const_dnp", "0.03", "--min_fetal_reads", "2"])
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads((output / "scientific-settings.json").read_text())["parameters"]
        self.assertEqual(settings["err_const_snp"], 0.06)
        self.assertEqual(settings["err_const_dnp"], 0.03)
        self.assertEqual(settings["min_fetal_reads"], 2)
        row, = table(output / "Summary_FetalFraction_CPI.csv", ",")
        self.assertEqual(float(row["Error_constant"]), settings["err_const_snp"])
        self.assertEqual(int(row["Min_fetal_reads"]), settings["min_fetal_reads"])

    def test_contamination_zero_flag_overrides_config_and_is_recorded(self):
        result, output = self.execute("contamination", {"include_zero": False}, ["--include_zero"])
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads((output / "scientific-settings.json").read_text())["parameters"]
        self.assertIs(settings["include_zero"], True)
        row, = table(output / "contamination_summary.txt")
        self.assertEqual(row["informative_sites"], "2")

    def test_contamination_conflicting_zero_flags_fail(self):
        result, output = self.execute("contamination", {}, ["--include_zero", "--exclude_zero"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("choose either", result.stderr)
        self.assertFalse((output / "contamination_summary.txt").exists())

    def test_cpi_empty_and_zero_coverage_are_distinct_from_malformed_total(self):
        for row, success in (("", True), ("chr1\t100\tA\tC\t0\t0\t0\tNA\n", True),
                             ("chr1\t100\tA\tC\t0\t0\t0\tbad\n", False)):
            with self.subTest(row=row), tempfile.TemporaryDirectory() as directory:
                inputs = Path(directory)
                for name in ("MotherM.txt", "FatherF.txt"):
                    (inputs / name).write_text("chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n" + row)
                result, output = self.execute("cpi", {}, inputs=inputs)
                self.assertEqual(result.returncode == 0, success, result.stderr)
                if success:
                    curve = output / "curves/MotherM-FatherF_SNPs_panel_1.tsv"
                    self.assertTrue(curve.read_text().startswith("Iteration\tInfSites_mother"))
