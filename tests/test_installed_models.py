"""Mutation tests for independent installed-model acceptance oracles."""

from collections import Counter
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("installed_models", ROOT / "scripts/acceptance/installed_models.py")
models = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(models)


class InstalledModelsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = self.root / "run"

    def write(self, name, contents):
        path = self.run / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents, encoding="utf-8")
        return path

    def pdf(self, name):
        self.write("output/" + name, b"%PDF-1.4\n" + b"fixture-content\n" * 10 + b"%%EOF\n")

    def settings(self, workflow, **overrides):
        # These are observed payload metadata, not expected numerical answers.
        registry = json.loads((ROOT / "src/newpat_scientific/settings_data.json").read_text())
        module = registry["workflows"][workflow]
        parameters = {name: entry["default"] for name, entry in module["parameters"].items()}
        parameters.update(overrides)
        record = {"schema_version": 1, "workflow": workflow, "parameters": parameters,
                  "constants": module["constants"]}
        for path in ("work/effective-scientific-settings.json", "output/scientific-settings.json"):
            self.write(path, json.dumps(record))

    def contamination(self, include_zero=True):
        self.settings("contamination", include_zero=include_zero)
        header = "individuo\tinformative_sites\tmean_contamination\tsd_contamination\n"
        self.write("output/contamination_summary.txt", header + (
            "Sample1\t2\t0.025\t0.0353553390593274\n" if include_zero else "Sample1\t1\t0.05\tNA\n"))
        self.write("output/contamination_Sample1.txt",
                   "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\tratio_REF_ALT\tratio_Other\tN_unexpected\tcontamination\n"
                   "chr1\t100\tA\tC\t95\t5\t11\t111\t0.95\t0.0990990990990991\t5\t0.05\n" + (
                       "chr1\t200\tA\tC\t100\t0\t0\t100\t1\t0\t0\t0\n" if include_zero else ""))

    def cpi(self):
        self.settings("cpi", min_fetal_reads=2)
        self.write("output/Summary_FetalFraction_CPI.csv",
                   "Pair,N_sites_mother,N_sites_father,Median_fetal_fraction_raw,Median_fetal_fraction_percent,"
                   "Max_logCPI,Min_logCPI,Median_logCPI,Mean_logCPI,CPI_medianFF,Error_constant,Min_fetal_reads,Min_fetal_percent,Marker_type\n"
                   "MotherM-FatherF_SNPs,3,3,0.06,6,1.301,0.301,0.602,0.735,0.602,0.001,2,NA,SNP\n"
                   "MotherN-FatherN_SNPs,0,0,NA,NA,NA,NA,NA,NA,NA,0.001,2,NA,SNP\n")
        header = "Iteration\tInfSites_mother\tInfSites_father\tCPI\tlog_CPI\tMismatch\tNotMismatch\tCutoff\n"
        self.write("output/curves/MotherM-FatherF_SNPs_panel_1.tsv", header +
                   "2\t3\t3\t20\t1.30102999566398\t0\t3\tALL\n"
                   "3\t2\t2\t4\t0.602059991327962\t0\t2\tALL\n"
                   "4\t1\t1\t2\t0.301029995663981\t0\t1\tALL\n")
        self.write("output/curves/MotherN-FatherN_SNPs_panel_1.tsv", header)
        for name in ("MotherM-FatherF_SNPs", "MotherN-FatherN_SNPs", "All"):
            self.pdf(f"plots/{name}_CPIplot.pdf" if name != "All" else "plots/All_CPIplots.pdf")

    def cpin(self):
        self.settings("cpin")
        identity = "MotherM-FatherF-ChildC_SNPs"
        header = ("Trio Marker_type N_sites N_hom_hom N_hom_het N_het_hom N_het_het Matching_sites "
                  "Mismatching_sites No_obligatory_allele_sites Maternal_incompatible_sites Log10_CPI CPI "
                  "Mismatch_probability Min_coverage Include_hom_hom Include_hom_het Include_het_hom Include_het_het")
        self.write("output/Summary_Postnatal_CPI.txt",
                   "\t".join(header.split()) + "\n" + identity +
                   "\tSNP\t5\t1\t3\t0\t1\t2\t2\t1\t1\t-4.885361220031512\t0.00001302083333333333"
                   "\t0.001\tNA\tTRUE\tTRUE\tTRUE\tTRUE\n")
        self.write(f"output/{identity}_sites.txt",
                   "chr\tpos\tStatus\tGenotype_combination\tPaternity_Index\tMismatch\tPaternal_transmission"
                   "\tRequired_paternal_allele\tPaternity_status\n"
                   "chr1\t100\teligible\thom_het\t1.25\tFALSE\t0.5\tALT\tmatch\n"
                   "chr1\t200\teligible\thom_het\t0.0025\tTRUE\t0\tALT\tmismatch\n"
                   "chr1\t300\teligible\thom_hom\t1.66666666666667\tFALSE\t1\tREF\tmatch\n"
                   "chr1\t400\tmother_child_incompatible\tNA\tNA\tNA\tNA\tNA\tNA\n"
                   "chr1\t500\teligible\thet_het\t1\tNA\tNA\tNA\tno_obligatory_allele\n"
                   "chr1\t600\teligible\thom_het\t0.0025\tTRUE\t0\tALT\tmismatch\n"
                   "chr1\t700\tquality_filter\tNA\tNA\tNA\tNA\tNA\tNA\n"
                   "chr1\t800\tquality_filter\tNA\tNA\tNA\tNA\tNA\tNA\n"
                   "chr1\t900\tfather_unassigned\thom_het\tNA\tNA\tNA\tALT\tNA\n")

    def mutate_table(self, name, row_index, column, value):
        path = self.run / "output" / name
        delimiter = "," if path.suffix == ".csv" else "\t"
        rows = list(csv.DictReader(io.StringIO(path.read_text()), delimiter=delimiter))
        rows[row_index][column] = value
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)

    def test_matrix_covers_44_positive_and_three_negative_cases_without_modifying_sources(self):
        fixtures = ROOT / "tests/fixtures"
        before = models.tree_hashes(fixtures / "five_modules")
        cases = models.build_cases(fixtures, self.root / "generated")
        self.assertEqual(len(cases), 47)
        self.assertEqual(len({case["id"] for case in cases}), 47)
        self.assertEqual(Counter(case["category"] for case in cases),
                         {"downstream-analytical": 26, "downstream-batch": 18, "invalid-input": 3})
        self.assertEqual(sum(callable(case["validate"]) for case in cases), 44)
        groups = {}
        for case in cases:
            self.assertTrue(callable(case["validate"]) or (case["validate"] is None and case["expect_failure"]))
            if "compare_group" in case:
                groups.setdefault(case["compare_group"], set()).add(case["mode"])
            paths = [argument for argument in case["args"] if isinstance(argument, Path)]
            self.assertTrue(paths and all(path.exists() and path.is_relative_to(self.root / "generated") for path in paths))
        self.assertEqual(len(groups), 6)
        self.assertTrue(all(modes == {"serial", "auto", "cap2"} for modes in groups.values()))
        self.assertEqual(models.tree_hashes(fixtures / "five_modules"), before)
        # The mismatch and metadata variants are applied only to their own copies.
        mismatch = self.root / "generated/models-snp-cpi-mismatch/FatherF.txt"
        self.assertEqual(models.table(mismatch, {"N_REF", "N_ALT"})[1]["N_ALT"], "0")
        baseline = self.root / "generated/models-snp-cpi-default/FatherF.txt"
        self.assertEqual(models.table(baseline, {"N_ALT"})[1]["N_ALT"], "50")
        self.assertIn("unused_metadata", (self.root / "generated/models-snp-cpi-metadata-na/population.tsv").read_text())
        batch = next(case for case in cases if case["id"] == "models-snp-cpin-batch3-auto")
        self.assertIn("M1:F1:C1,M2:F2:C2,M3:F3:C3", batch["args"])
        with self.assertRaises(FileExistsError):
            models.build_cases(fixtures, self.root / "generated")

    def test_expected_invalid_inputs_match_the_real_cli_diagnostic_before_execution(self):
        cases = models.build_cases(ROOT / "tests/fixtures", self.root / "generated")
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "NIPAT_PROJECT_DIR": str(ROOT),
                       "NIPAT_WORKSPACE_DIR": str(self.root), "NIPAT_DATA_DIR": str(self.root / "data"),
                       "NIPAT_RUNS_DIR": str(self.root / "runs"), "NIPAT_BACKEND": "native"}
        if os.name == "nt":
            environment.update(NIPAT_BACKEND="wsl", NIPAT_WSL_DISTRO="NIPAT-Desktop-test")
        for case in (item for item in cases if item.get("expect_failure")):
            with self.subTest(case=case["id"]):
                result = subprocess.run([sys.executable, "-m", "newpat", "--dry-run", *map(str, case["args"]),
                                         "--run-name", case["id"]],
                                        env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stderr, case["expect_failure"])
                for unrelated in ("Docker unavailable", "WSL failed", "Python import failed"):
                    self.assertNotRegex(unrelated, case["expect_failure"])
        self.assertFalse(list((self.root / "runs").rglob("run.json")))

    def test_all_three_independent_positive_readouts_pass(self):
        for workflow in ("contamination", "cpi", "cpin"):
            with self.subTest(workflow=workflow):
                self.run = self.root / workflow
                getattr(self, workflow)()
                result = models.validate_model(self.run, workflow=workflow, marker="SNP")
                self.assertTrue(result["scientific_sha256"])
                self.assertEqual(result["summary_rows"], 2 if workflow == "cpi" else 1)
                json.dumps(result)

    def test_contamination_rejects_wrong_other_denominator_and_false_zero_sd(self):
        self.contamination()
        self.mutate_table("contamination_Sample1.txt", 0, "ratio_Other", "0.11")
        with self.assertRaisesRegex(ValueError, "ratio_Other"):
            models.validate_model(self.run, workflow="contamination", marker="SNP")
        self.contamination(include_zero=False)
        models.validate_model(self.run, workflow="contamination", marker="SNP", include_zero=False)
        self.mutate_table("contamination_summary.txt", 0, "sd_contamination", "0")
        with self.assertRaisesRegex(ValueError, "expected explicit NA"):
            models.validate_model(self.run, workflow="contamination", marker="SNP", include_zero=False)

    def test_cpi_rejects_zero_in_place_of_no_sites_na(self):
        self.cpi()
        self.mutate_table("Summary_FetalFraction_CPI.csv", 1, "CPI_medianFF", "0")
        with self.assertRaisesRegex(ValueError, "expected explicit NA"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")

    def test_cpi_rejects_missing_or_numerically_changed_curve(self):
        self.cpi()
        name = "curves/MotherM-FatherF_SNPs_panel_1.tsv"
        self.mutate_table(name, 1, "CPI", "4.01")
        with self.assertRaisesRegex(ValueError, "CPI curve"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")
        self.cpi()
        (self.run / "output" / name).unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")

    def test_cpin_rejects_site_mismatch_or_wrong_exclusion(self):
        name = "MotherM-FatherF-ChildC_SNPs_sites.txt"
        for row, column, value in ((1, "Paternity_Index", "1.25"), (6, "Status", "eligible"),
                                   (3, "Paternity_Index", "0"), (0, "Required_paternal_allele", "REF")):
            with self.subTest(column=column, row=row):
                self.cpin()
                self.mutate_table(name, row, column, value)
                with self.assertRaises(ValueError):
                    models.validate_model(self.run, workflow="cpin", marker="SNP")

    def test_cpin_requires_one_scalar_per_trio_and_rejects_obsolete_curves(self):
        self.cpin()
        path = self.run / "output/Summary_Postnatal_CPI.txt"
        text = path.read_text()
        path.write_text(text + text.splitlines(keepends=True)[1])
        with self.assertRaisesRegex(ValueError, "duplicated"):
            models.validate_model(self.run, workflow="cpin", marker="SNP")
        self.cpin()
        self.write("output/curves/obsolete.tsv", "unexpected")
        with self.assertRaisesRegex(ValueError, "Unexpected postnatal threshold curve"):
            models.validate_model(self.run, workflow="cpin", marker="SNP")

    def test_cpi_rejects_an_active_percent_reported_instead_of_na(self):
        self.cpi()
        self.mutate_table("Summary_FetalFraction_CPI.csv", 0, "Min_fetal_percent", "0")
        with self.assertRaisesRegex(ValueError, "Min_fetal_percent"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")

    def test_settings_cannot_pass_just_because_both_candidate_records_agree(self):
        self.cpi()
        self.settings("cpi", min_fetal_reads=2, err_const_snp=.01)
        with self.assertRaisesRegex(ValueError, "settings/err_const_snp"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")

    def test_missing_or_truncated_pdf_is_not_scientific_success(self):
        self.cpi()
        self.write("output/plots/All_CPIplots.pdf", b"%PDF-1.4\n")
        with self.assertRaisesRegex(ValueError, "incomplete analytical PDF"):
            models.validate_model(self.run, workflow="cpi", marker="SNP")
        self.run = self.root / "postnatal"
        self.cpin()
        self.pdf("All_CPIplots.pdf")
        with self.assertRaisesRegex(ValueError, "unexpected analytical PDF"):
            models.validate_model(self.run, workflow="cpin", marker="SNP")

    def test_input_mutation_fails_before_validating_a_run(self):
        case = models.build_cases(ROOT / "tests/fixtures", self.root / "generated")[0]
        path = self.root / "generated" / case["id"] / "MotherM.txt"
        path.write_text("modified input\n")
        with self.assertRaisesRegex(ValueError, "modified an original"):
            case["validate"](self.root / "no-run")

    def test_numeric_comparison_rejects_nonfinite_and_boolean_values(self):
        for value in ("nan", "Inf", "-Inf", True, "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                models.number(value, 1, "oracle")


if __name__ == "__main__":
    unittest.main()
