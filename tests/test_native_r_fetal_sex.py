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
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
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
        if "NEWPAT_NATIVE_TEST_PAYLOAD_ROOT" in os.environ:
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
        for layout in ("split", "combined", "registered-combined", "registered-split"):
            with self.subTest(layout=layout):
                self.check_shared_maternal_dnp(layout)

    def check_shared_maternal_dnp(self, layout):
        combined = layout.endswith("combined")
        registered = layout.startswith("registered")
        inputs = (combined_example("Female_fetus", self.root) if combined
                  else example("Female_fetus"))
        maternal = "dnp_Maternal"
        panel = self.root / "panel.tsv"
        panel.write_text("chr\tpos1\tpos2\nchr1\t3010000\t3010001\nchr1\t3020000\t3020001\n",
                         encoding="utf-8")
        role_ids = {"autosomes": maternal, "x": "fsx_Maternal", "y": "fsy_Maternal"}
        if combined:
            role_ids = {"dnp": maternal, "y": "fsy_Maternal"}
        if registered and combined:
            with Path(inputs["dnp"]).open("a", encoding="utf-8") as stream:
                stream.write("chrY\t61\t62\tGC\tTT\t7\t0\t0\t7\n")
        if registered:
            snp = self.root / "maternal_snp.tsv"
            snp.write_text(Path(inputs["y"]).read_text() + "chr1\t21\tG\tT\t1\t0\t0\t1\n")
            inputs["y"] = str(snp)
        originals = {role: Path(path).read_bytes() for role, path in inputs.items()}
        plan = {"schema_version": 1,
                "samples": [{"id": identifier, "kind": "snp-table" if role == "y" else "dnp-table",
                             "path": inputs[role]} for role, identifier in role_ids.items()],
                "steps": [{"id": "contamination", "workflow": "contamination",
                           "inputs": {"samples": [{"sample": maternal}], "panel": str(panel)}, "parameters": {}},
                          {"id": "sex", "workflow": "fetal-sex", "inputs": role_ids,
                           "parameters": {"project_regions": True} if registered else {}}]}
        plan["presentation"] = {"samples": {sid: Path(inputs[role]).name for role, sid in role_ids.items()},
                                "pairs": {}}
        manifest = self.root / "plan.json"
        manifest.write_text(json.dumps(plan), encoding="utf-8")
        run = self.root / layout
        result = subprocess.run(
            [sys.executable, str(PAYLOAD / "engine/main.py"), "execute-plan",
             "--plan", str(manifest), "--run-dir", str(run)],
            env=dict(os.environ, NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R")),
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
        self.assertEqual({role: Path(path).read_bytes() for role, path in inputs.items()}, originals)
        self.assertEqual((run / "steps/contamination/work/inputs/table_0001.txt").read_bytes(),
                         originals["dnp" if combined else "autosomes"])
        with (run / "steps/contamination/output/contamination_summary.txt").open(encoding="utf-8") as stream:
            row, = csv.DictReader(stream, delimiter="\t")
        self.assertEqual(row["informative_sites"], "2")
        self.assertAlmostEqual(float(row["mean_contamination"]), 0.02)

    @unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
    @unittest.skipUnless(shutil.which("samtools"), "samtools required to build a synthetic maternal BAM")
    def test_maternal_bam_to_fetal_sex_matches_reimported_tables(self):
        fasta = self.root / "genome.fa"
        sam = self.root / "reads.sam"
        bam = self.root / "sample_0001.bam"
        recipe = (("chr1", 94, 6), ("chrX", 98, 2), ("chrY", 12, 0))
        fasta.write_text("".join(f">{chrom}\nGACT\n" for chrom, _, _ in recipe))
        with sam.open("w") as stream:
            stream.write("@HD\tVN:1.6\tSO:coordinate\n")
            for chrom, _, _ in recipe:
                stream.write(f"@SQ\tSN:{chrom}\tLN:4\n")
            for chrom, n_ref, n_alt in recipe:
                for index, allele in enumerate(["AC"] * n_ref + ["GT"] * n_alt):
                    stream.write(f"{chrom}_{index}\t0\t{chrom}\t1\t60\t4M\t*\t0\t0\tG{allele}T\tIIII\n")
        for args in (["faidx", fasta], ["view", "-bo", bam, sam], ["index", bam]):
            subprocess.run(["samtools", *args], check=True, capture_output=True)

        dnp, snp = self.root / "dnp.tsv", self.root / "snp.tsv"
        dnp.write_text("chr1\t2\t3\tAC\tGT\nchrX\t2\t3\tAC\tGT\n")
        snp.write_text("chr\tpos\tref\talt\nchr1\t2\tA\tG\nchrY\t2\tA\tG\n")
        settings = {"scientific_settings": {"baq": False}}
        plan = {"schema_version": 1, "samples": [{"id": "mother", "kind": "bam", "path": str(bam)}],
                "steps": [
                    {"id": "dnp", "workflow": "dnp-call", "inputs": {
                        "samples": ["mother"], "reference": str(fasta), "panel": str(dnp)},
                     "parameters": {"parallel": True, **settings}},
                    {"id": "snp", "workflow": "snp-call", "inputs": {
                        "sample": "mother", "reference": str(fasta), "panel": str(snp)},
                     "parameters": {"mode": "bam", **settings}},
                    {"id": "sex", "workflow": "fetal-sex", "inputs": {
                        "dnp": {"step": "dnp", "output": "dnp-tables", "sample": "mother"},
                        "y": {"step": "snp", "output": "snp-tables", "sample": "mother"}}, "parameters": {}}]}
        manifest = self.root / "plan.json"
        manifest.write_text(json.dumps(plan))
        run = self.root / "generated"
        result = subprocess.run([sys.executable, str(PAYLOAD / "engine/main.py"), "execute-plan",
                                 "--plan", str(manifest), "--run-dir", str(run)],
                                env=dict(os.environ, NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                                         NEWPAT_PLOTS_HELPER=str(HELPERS / "plots.R"),
                                         NEWPAT_DNP_BLOCKS_HELPER=str(HELPERS / "dnp_blocks.R")),
                                capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr +
                         "".join(log.read_text()[-2000:] for log in run.glob("steps/*/command.log")))
        steps = {s["id"]: s for s in json.loads((run / "workflow-state.json").read_text())["steps"]}
        dnp_counts = run / steps["dnp"]["artifacts"]["dnp-tables"][0]["path"]
        snp_counts = run / steps["snp"]["artifacts"]["snp-tables"][0]["path"]
        with snp_counts.open() as stream:
            reader = csv.DictReader(stream, delimiter="\t")
            rows = list(reader)
        self.assertEqual({r["chr"] for r in rows}, {"chr1", "chrY"})
        y_counts = self.root / "maternal_Y.txt"
        with y_counts.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=reader.fieldnames, delimiter="\t")
            writer.writeheader()
            writer.writerows(row for row in rows if row["chr"] == "chrY")
        # Standalone table mode derives the biological sample name from the DNP filename.
        named_dnp = self.root / "full_output_mother.txt"
        shutil.copyfile(dnp_counts, named_dnp)
        direct = self.root / "imported"
        result = execute_workflow("fetal-sex", direct, dnp=str(named_dnp), y=str(y_counts))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        observed = run / "steps/sex/output"
        with (observed / "Fetal_sex_summary.txt").open() as stream:
            summary, = csv.DictReader(stream, delimiter="\t")
        self.assertEqual([summary[k] for k in ("Fetal_reads_A", "Fetal_reads_X", "Reads_Y", "Fetal_sex")],
                         ["6", "2", "12", "M"])
        for source in (FIXTURE / "outputs/Male_fetus").glob("*.txt"):
            self.assertEqual((observed / source.name).read_bytes(), (direct / "output" / source.name).read_bytes(),
                             source.name)

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
