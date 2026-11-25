"""Installed postnatal CPI settings, genotype combinations and coverage boundaries."""

import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest

import test_native_r_edge_cases as native
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class NativeCPINParameterTests(unittest.TestCase):
    def execute(self, root, marker, settings=None, options=(), huge_support=False):
        inputs = root / "inputs"
        shutil.copytree(native.ROOT / "tests/fixtures/cpin" / marker, inputs)
        if huge_support:
            child = inputs / "ChildC1.txt"
            before = child.read_text()
            after = before.replace("100\t0\t0\t100", "1000000000\t0\t0\t1000000000")
            self.assertNotEqual(before, after, "The large-support fixture must actually change")
            child.write_text(after)
        original = {path.name: path.read_bytes() for path in inputs.iterdir()}
        process, output = native.NativeREdgeCases.run_native(
            self, root, "cpin", inputs, native_options=options, settings=settings)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(original, {path.name: path.read_bytes() for path in inputs.iterdir()})
        document = json.loads((output / "scientific-settings.json").read_text())
        self.assertEqual(document["workflow"], "cpin")
        self.assertEqual(document["constants"]["ploidy"]["value"], 2)
        for name, value in (settings or {}).items():
            self.assertEqual(document["parameters"][name], value)
        return output, document

    def test_parameter_effects_are_observed_in_native_snp_and_dnp_results(self):
        variants = (
            ({"min_coverage": 2}, 5),           # includes the child with total depth 2
            ({"min_coverage": 3}, 4),
            ({"min_coverage": 101}, 0),
            ({"other_fraction_max": .11}, 6),
            ({"heterozygous_max": .7}, 6),
            ({"include_hom_hom": False}, 4),
            ({"include_hom_het": False}, 2),
            ({"include_het_het": False}, 4),
        )
        for marker in ("SNP", "DNP"):
            for settings, count in variants:
                with self.subTest(marker=marker, settings=settings), tempfile.TemporaryDirectory() as temporary:
                    output, _ = self.execute(Path(temporary), marker, settings=settings)
                    row, = native.table(output / "Summary_Postnatal_CPI.txt")
                    self.assertEqual(int(row["N_sites"]), count)
                    self.assertEqual(row["Marker_type"], marker)
                    if count == 0:
                        self.assertEqual((row["CPI"], row["Log10_CPI"]), ("NA", "NA"))
                    self.assertFalse((output / "curves").exists())
                    self.assertFalse(any(output.rglob("*.pdf")))

    def test_custom_mismatch_probabilities_change_the_scientific_formula(self):
        for marker in ("SNP", "DNP"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temporary:
                epsilon = .02
                output, _ = self.execute(Path(temporary), marker,
                                         settings={f"mismatch_probability_{marker.lower()}": epsilon})
                row, = native.table(output / "Summary_Postnatal_CPI.txt")
                expected = 1.25 * (epsilon / .4) ** 2 / .6
                self.assertTrue(math.isclose(float(row["CPI"]), expected, rel_tol=1e-12))
                self.assertAlmostEqual(float(row["Log10_CPI"]), math.log10(expected))
                self.assertEqual(float(row["Mismatch_probability"]), epsilon)

    def test_native_cli_overrides_are_recorded_and_used(self):
        with tempfile.TemporaryDirectory() as temporary:
            output, document = self.execute(Path(temporary), "SNP", options=(
                "--min_coverage", "3", "--mismatch_probability_snp", ".02", "--include_het_het", "FALSE"))
            self.assertEqual(document["parameters"]["min_coverage"], 3)
            self.assertEqual(document["parameters"]["mismatch_probability_snp"], .02)
            self.assertIs(document["parameters"]["include_het_het"], False)
            row, = native.table(output / "Summary_Postnatal_CPI.txt")
            self.assertEqual((row["Min_coverage"], row["N_sites"], row["Include_het_het"]), ("3", "3", "FALSE"))
            self.assertTrue(math.isclose(float(row["CPI"]), 1.25 * .02 / .4 / .6, rel_tol=1e-12))

    def test_billion_read_depth_yields_one_scalar_and_no_support_curve(self):
        for marker in ("SNP", "DNP"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temporary:
                output, _ = self.execute(Path(temporary), marker, huge_support=True)
                row, = native.table(output / "Summary_Postnatal_CPI.txt")
                epsilon = .001 if marker == "SNP" else .0000892303778101497
                self.assertTrue(math.isclose(float(row["CPI"]), 1.25 * (epsilon / .4)**2 / .6, rel_tol=1e-12))
                self.assertFalse((output / "curves").exists())

    def test_coverage_must_pass_separately_in_all_trio_members(self):
        for role in ("mother", "father", "child"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                inputs = root / "inputs"
                inputs.mkdir()
                header = "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\n"
                for who, stem in (("mother", "MotherM1"), ("father", "FatherF1"), ("child", "ChildC1")):
                    # Locus 1 is just below the minimum for one person. Locus 2
                    # reaches 10 reads only when its single Other read is counted.
                    first = "9\t0\t0\t9" if who == role else "10\t0\t0\t10"
                    (inputs / f"{stem}.txt").write_text(
                        header + f"chr1\t1\tA\tG\t{first}\nchr1\t2\tA\tG\t9\t0\t1\t10\n")
                (inputs / "population.txt").write_text(
                    "chr\tpos\tRef_f.pop\tAlt_f.pop\nchr1\t1\t0.5\t0.5\nchr1\t2\t0.5\t0.5\n")
                process, output = native.NativeREdgeCases.run_native(
                    self, root, "cpin", inputs, settings={"min_coverage": 10})
                self.assertEqual(process.returncode, 0, process.stderr)
                row, = native.table(output / "Summary_Postnatal_CPI.txt")
                self.assertEqual((row["N_sites"], float(row["CPI"])), ("1", 2.0))
                sites = {site["pos"]: site for site in native.table(next(output.glob("*_sites.txt")))}
                self.assertEqual(sites["1"]["Status"], "quality_filter")
                self.assertEqual(sites["1"][f"Quality_pass_{role}"], "FALSE")
                self.assertEqual(sites["2"]["Status"], "eligible")

    def test_all_combinations_disabled_is_invalid(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            shutil.copytree(native.ROOT / "tests/fixtures/cpin/SNP", inputs)
            options = tuple(value for group in ("hom_hom", "hom_het", "het_hom", "het_het")
                            for value in (f"--include_{group}", "FALSE"))
            process, output = native.NativeREdgeCases.run_native(self, root, "cpin", inputs, options)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("combination", process.stderr.lower())
            self.assertFalse((output / "Summary_Postnatal_CPI.txt").exists())


if __name__ == "__main__":
    unittest.main()
