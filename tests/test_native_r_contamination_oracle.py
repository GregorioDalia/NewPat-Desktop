"""Exact per-site, sample mean and sample SD oracles over input count grids."""

from fractions import Fraction
import math
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import unittest

from newpat_scientific.settings import settings_context

from downstream_oracle_tables import alleles, coordinate, coordinate_header, write_table
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON
from test_native_r_edge_cases import HELPERS, PAYLOAD, table


def write_samples(inputs, marker):
    inputs.mkdir()
    header = (*coordinate_header(marker), "N_REF", "N_ALT", "N_Other", "ratio_REF_ALT")
    panel = []
    grid = []
    # Each depth stratum spans all 91 possible REF counts out of 90.
    # REF-dependent depth distinguishes the arithmetic mean from a pooled read fraction.
    for group, other in enumerate((0, 10, 11, 24)):
        for ref in range(91):
            locus = 1 + 91 * group + ref
            coord = coordinate(marker, locus)
            panel.append(coord)
            copies = 3 if 9 <= ref <= 70 else 1
            grid.append((*coord, ref * copies, (90 - ref) * copies, other * copies, 0.5))
    # Same positions, different contig. Neither row can enter the panel.
    grid.extend([("1", *coordinate(marker, 1)[1:], 90, 0, 0, 0.5),
                 ("1", *coordinate(marker, 3)[1:], 88, 2, 0, 0.5)])
    write_table(inputs / "grid.txt", header, reversed(grid))
    start = coordinate(marker, 1)
    write_table(inputs / "single.txt", (*header, "REF", "ALT"), [(*start, 89, 1, 0, 0.5, *alleles(marker))])
    write_table(inputs / "zero.txt", header, [(*start, 0, 90, 0, 0.5)])
    write_table(inputs / "no_support.txt", header, [(*start, 0, 0, 25, 0.5)])
    write_table(inputs / "empty.txt", header, [])
    return panel


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class ContaminationOracles(unittest.TestCase):
    def check_sample(self, output, name, summary, expected):
        rows = table(output / f"contamination_{name}.txt")
        # Keep chromosome as a string and both DNP positions in the key.
        observed = {}
        for row in rows:
            positions = ("pos",) if "pos" in row else ("pos1", "pos2")
            key = (row["chr"], *(int(row[pos]) for pos in positions))
            self.assertNotIn(key, observed)
            observed[key] = (int(row["N_unexpected"]), float(row["contamination"]))
        self.assertEqual(observed.keys(), expected.keys())
        for locus, (unexpected, value) in expected.items():
            with self.subTest(sample=name, locus=locus):
                self.assertEqual(observed[locus][0], unexpected)
                self.assertAlmostEqual(observed[locus][1], float(value), places=12)
        values = [value for _, value in expected.values()]
        self.assertEqual(int(summary["informative_sites"]), len(values))
        for column, value in (("mean_contamination", statistics.mean(values) if values else None),
                              ("sd_contamination", statistics.stdev(values) if len(values) > 1 else None)):
            if value is None:
                self.assertEqual(summary[column], "NA")
            else:
                self.assertTrue(math.isclose(float(summary[column]), float(value), rel_tol=1e-12, abs_tol=1e-14),
                                (name, column, value, summary[column]))

    def test_exact_grid_at_and_on_both_sides_of_cutoffs(self):
        # Truth given directly in integer grid coordinates. The baseline Other
        # boundary is 10/(90+10), not 10/90. The two relaxed genotype limits
        # are asymmetric to catch swapped or incorrectly shared cutoffs.
        profiles = (
            ({}, (0, 1), 9, 81, True),
            ({"other_fraction_max": .2, "homozygous_alt_max": .2,
              "homozygous_ref_min": .7, "include_zero": False}, (0, 1, 2), 18, 63, False),
            ({"other_fraction_max": 0, "homozygous_alt_max": .02,
              "homozygous_ref_min": .98, "include_zero": True}, (0,), 1, 89, True),
        )
        for marker in ("SNP", "DNP"):
            for settings, groups, alt_end, ref_begin, include_zero in profiles:
                with self.subTest(marker=marker, settings=settings), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    inputs = root / "samples"
                    panel = root / "panel.tsv"
                    write_table(panel, coordinate_header(marker) if marker == "SNP" else None, write_samples(inputs, marker))
                    output = root / "output"
                    script = PAYLOAD / "scientific/vendor/NEWPAT/contamination/detect_contamination.R"
                    with settings_context("contamination", settings, root / "work"):
                        env = dict(os.environ, NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                                   NEWPAT_EXECUTION_MODE="serial")
                        process = subprocess.run(["Rscript", str(script), str(panel), str(inputs), str(output)],
                                                 env=env, text=True, capture_output=True, timeout=90)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    expected = {}
                    for group in groups:
                        for ref in (*range(alt_end + 1), *range(ref_begin, 91)):
                            minor = min(ref, 90 - ref)
                            if include_zero or minor:
                                locus = 1 + 91 * group + ref
                                copies = 3 if 9 <= ref <= 70 else 1
                                expected[coordinate(marker, locus)] = (minor * copies, Fraction(minor, 90))
                    summaries = {row["individuo"]: row for row in table(output / "contamination_summary.txt")}
                    self.assertEqual(summaries.keys(), {"grid", "single", "zero", "empty", "no_support"})
                    single, = table(output / "contamination_single.txt")
                    self.assertEqual((single["REF"], single["ALT"]), alleles(marker))
                    start = coordinate(marker, 1)
                    for name, rows in (("grid", expected), ("single", {start: (1, Fraction(1, 90))}),
                                       ("zero", {start: (0, Fraction(0))} if include_zero else {}),
                                       ("empty", {}), ("no_support", {})):
                        self.check_sample(output, name, summaries[name], rows)

    def test_boolean_count_is_not_a_read(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            panel, sample, output = root / "panel.tsv", root / "sample.txt", root / "output"
            write_table(panel, ("chr", "pos"), [("chr1", 3)])
            write_table(sample, ("chr", "pos", "N_REF", "N_ALT", "N_Other"), [("chr1", 3, "T", 0, 0)])
            script = PAYLOAD / "scientific/vendor/NEWPAT/contamination/detect_contamination.R"
            with settings_context("contamination", {}, root / "work"):
                env = dict(os.environ, NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                           NEWPAT_EXECUTION_MODE="serial")
                proc = subprocess.run(["Rscript", str(script), str(panel), str(sample), str(output)],
                                      env=env, text=True, capture_output=True, timeout=90)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("counts must be finite nonnegative integers", proc.stderr)
            self.assertFalse((output / "contamination_summary.txt").exists())
