"""Independent rational-product oracles for both marker types and every fetal-support threshold."""

from fractions import Fraction
import math
from pathlib import Path
import statistics
import tempfile
import unittest

import test_native_r_edge_cases as native
from downstream_oracle_tables import alleles, coordinate, coordinate_header, write_calls, write_table
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON


# Maternal and paternal REF, ALT, Other; frequency of the reference allele.
# Loci 1..6 exercise both maternal homozygotes x all three paternal genotypes.
# Loci 7..12 isolate Other filtering in each parent, unassigned or absent fathers,
# relaxed maternal classification and an inclusive maternal Other/total of 10%.
INPUT = (
    ((98, 2, 0), (10, 90, 0), ".75"),
    ((3, 97, 0), (40, 60, 0), ".125"),
    ((96, 4, 0), (90, 10, 0), ".6"),
    ((5, 95, 0), (10, 90, 0), ".2"),
    ((94, 6, 0), (60, 40, 0), ".5"),
    ((7, 93, 0), (90, 10, 0), ".4"),
    ((90, 10, 0), (0, 100, 12), ".75"),
    ((8, 92, 15), (100, 0, 0), ".4"),
    ((95, 5, 0), (65, 35, 0), ".6"),
    ((88, 12, 0), (19, 81, 0), ".8"),
    ((81, 9, 10), (50, 50, 0), ".75"),
    ((7, 93, 0), None, ".5"),
    ((0, 0, 0), (0, 0, 0), ".5"),
)


def make_inputs(inputs, marker, swapped):
    inputs.mkdir()
    loci = list(enumerate(INPUT, start=1))
    # Different orders in each table make accidental joins by row detectable.
    for name, index in (("MotherM1", 0), ("FatherF1", 1)):
        source = reversed(loci) if index == 1 else loci
        write_calls(inputs / f"{name}.txt", marker,
                    [(locus, values[index]) for locus, values in source if values[index] is not None],
                    swap=swapped)
    bases = alleles(marker)
    rows = []
    for locus, (_, _, ref_text) in loci[::2] + loci[1::2]:
        ref = Fraction(ref_text)
        if swapped:
            ref = 1 - ref
        fractions = [str(float(value)).replace(".", "," if swapped else ".") for value in (ref, 1 - ref)]
        rows.append((*coordinate(marker, locus), *(bases[::-1] if swapped else bases), *fractions))
    write_table(inputs / "population.txt", (*coordinate_header(marker), "REF", "ALT", "Ref_f.pop", "Alt_f.pop"), rows)
    for panel, group in (("core", range(1, 7)), ("edge", range(7, 14))):
        write_table(inputs / f"{panel}.tsv", (*coordinate_header(marker), "REF", "ALT"),
                    ((*coordinate(marker, locus), *(bases[::-1] if swapped else bases)) for locus in group))


def expected_loci(relaxed, error):
    # Independent truth by construction, not a second implementation of the R filters.
    # (locus, support, maternal REF+ALT, status after maternal selection, PI).
    truth = [
        (1, 2, 100, "match", Fraction(4)),
        (2, 3, 100, "match", Fraction(4)),
        (3, 4, 100, "mismatch", error / Fraction(".4")),
        (4, 5, 100, "mismatch", error / Fraction(".2")),
        (5, 6, 100, "match", Fraction(1)),
        (6, 7, 100, "match", Fraction("2.5")),
        (7, 10, 100, "match" if relaxed else "no_father", Fraction(4) if relaxed else None),
        (9, 5, 100, "match" if relaxed else "unassigned", Fraction("1.25") if relaxed else None),
        (11, 9, 90, "match", Fraction(2)),
        (12, 7, 100, "no_father", None),
    ]
    if relaxed:
        truth.append((10, 12, 100, "match", Fraction(5)))
    return truth


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class PrenatalOracles(unittest.TestCase):
    def check_panel(self, output, marker, index, panel, summary, loci, minimum):
        curves = native.table(output / f"curves/MotherM1-FatherF1_{marker}s_panel_{index}.tsv")
        sites = [row for row in loci if row[1] >= minimum]
        thresholds = list(range(minimum, max(row[1] for row in sites) + 1))
        self.assertEqual([int(row["Iteration"]) for row in curves], thresholds)
        self.assertEqual({row["Cutoff"] for row in curves}, {panel})
        logs = {}
        for threshold, row in zip(thresholds, curves, strict=True):
            with self.subTest(panel=panel, threshold=threshold):
                selected = [site for site in sites if site[1] >= threshold]
                factors = [site[4] for site in selected if site[4] is not None]
                mismatch_count = sum(site[3] == "mismatch" for site in selected)
                non_mismatch = sum(site[3] in ("match", "unassigned") for site in selected)
                self.assertEqual(int(row["InfSites_mother"]), len(selected))
                self.assertEqual(int(row["InfSites_father"]), len(factors))
                self.assertEqual(int(row["Mismatch"]), mismatch_count)
                self.assertEqual(int(row["NotMismatch"]), non_mismatch)
                if factors:
                    exact = math.prod(factors)
                    logs[threshold] = math.log10(exact)
                    self.assertTrue(math.isclose(float(row["CPI"]), float(exact), rel_tol=1e-12), row)
                    self.assertAlmostEqual(float(row["log_CPI"]), logs[threshold], places=12)
                else:
                    self.assertEqual((row["CPI"], row["log_CPI"]), ("NA", "NA"))

        self.assertEqual(int(summary["N_sites_mother"]), len(sites))
        self.assertEqual(int(summary["N_sites_father"]), sum(site[3] != "no_father" for site in sites))
        ff = statistics.median(Fraction(2 * support, depth) for _, support, depth, _, _ in sites)
        self.assertEqual(float(summary["Median_fetal_fraction_raw"]), round(float(ff), 4))
        self.assertEqual(float(summary["Median_fetal_fraction_percent"]), round(float(100 * ff), 2))
        values = list(logs.values())
        median_support = round(statistics.median(site[1] for site in sites))
        for column, expected in (("Max_logCPI", max(values)), ("Min_logCPI", min(values)),
                                 ("Mean_logCPI", statistics.mean(values)), ("Median_logCPI", statistics.median(values)),
                                 ("CPI_medianFF", logs.get(median_support))):
            if expected is None:
                self.assertEqual(summary[column], "NA")
            else:
                self.assertAlmostEqual(float(summary[column]), round(expected, 3), places=10, msg=column)

    def test_threshold_curves_and_summaries(self):
        for marker in ("SNP", "DNP"):
            for profile in ("baseline", "alleles_swapped", "relaxed"):
                with self.subTest(marker=marker, profile=profile), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    inputs = root / "inputs"
                    make_inputs(inputs, marker, profile == "alleles_swapped")
                    relaxed = profile == "relaxed"
                    minimum = 4 if relaxed else 2
                    settings = {"min_fetal_reads": minimum, "err_const_snp": .008, "err_const_dnp": .015}
                    if relaxed:
                        settings.update(other_fraction_max=.12, homozygous_ref_min=.8, homozygous_alt_max=.2,
                                        heterozygous_min=.35, heterozygous_max=.65)
                    panels = ",".join(f"{name}={inputs / (name + '.tsv')}" for name in ("core", "edge"))
                    process, output = native.NativeREdgeCases.run_native(
                        self, root, "cpi", inputs, ("--cutoff_map", panels), settings)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    error = Fraction(".008") if marker == "SNP" else Fraction(".015")
                    truth = expected_loci(relaxed, error)
                    summaries = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
                    self.assertEqual([s["Cutoff"] for s in summaries], ["core", "edge"])
                    for index, summary in enumerate(summaries, start=1):
                        self.assertEqual(summary["Marker_type"], marker)
                        self.assertEqual(float(summary["Error_constant"]), float(error))
                        self.assertEqual(int(summary["Min_fetal_reads"]), minimum)
                        subset = [row for row in truth if (row[0] <= 6) == (index == 1)]
                        self.check_panel(output, marker, index, summary["Cutoff"], summary, subset, minimum)

    def test_invalid_frequency_or_count_produces_no_summary(self):
        # Zero is invalid for an explicitly supplied allele frequency. It would
        # otherwise introduce division by zero or an infinite log-CPI.
        for field, bad_value, message in (
            ("Alt_f.pop", "0", "Population frequencies must be finite and in (0, 1]"),
            ("Ref_f.pop", "-0.1", "Population frequencies must be finite and in (0, 1]"),
            ("Ref_f.pop", "1.01", "Population frequencies must be finite and in (0, 1]"),
            ("N_REF", "T", "counts must be finite nonnegative integers"),
        ):
            with self.subTest(field=field, value=bad_value), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = root / "inputs"
                inputs.mkdir()
                head = ("chr", "pos", "REF", "ALT")
                counts = (*head, "N_REF", "N_ALT", "N_Other", "total_count")
                site = ("chr1", 3, "A", "G")
                mother = (*site, 95, 5, 0, 100)
                father = (*site, bad_value, 99, 0, 100) if field == "N_REF" else (*site, 0, 100, 0, 100)
                write_table(inputs / "MotherM1.txt", counts, [mother])
                write_table(inputs / "FatherF1.txt", counts, [father])
                refs = bad_value if field == "Ref_f.pop" else ".75"
                alts = bad_value if field == "Alt_f.pop" else ".25"
                write_table(inputs / "population.txt", (*head, "Ref_f.pop", "Alt_f.pop"), [(*site, refs, alts)])
                result, output = native.NativeREdgeCases.run_native(self, root, "cpi", inputs)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse((output / "Summary_FetalFraction_CPI.csv").exists())

    def test_headerless_snp_panel_preserves_na_contig_and_uncovered_total(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inputs = root / "inputs"
            inputs.mkdir()
            # Each SNP is on a contig literally named NA. The same two letters
            # in total_count for zero coverage represent a missing measurement.
            for parent, reads in (("MotherM1", (95, 5, 0)), ("FatherF1", (0, 100, 0))):
                write_calls(inputs / f"{parent}.txt", "SNP", [(3, reads), (6, (0, 0, 0))])
            markers = [(*coordinate("SNP", site), *alleles("SNP")) for site in (3, 6)]
            write_table(inputs / "panel.tsv", None, markers)
            write_table(inputs / "population.txt", ("chr", "pos", "REF", "ALT", "Ref_f.pop", "Alt_f.pop"),
                        ((*row, .8, .2) for row in markers))
            result, output = native.NativeREdgeCases.run_native(
                self, root, "cpi", inputs, ("--markers", str(inputs / "panel.tsv")))
            self.assertEqual(result.returncode, 0, result.stderr)
            summary, = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
            self.assertEqual((summary["N_sites_mother"], summary["N_sites_father"]), ("1", "1"))
            rows = native.table(next((output / "curves").glob("*.tsv")))
            self.assertEqual([int(row["Iteration"]) for row in rows], [2, 3, 4, 5])
            self.assertTrue(all(math.isclose(float(row["CPI"]), 5, rel_tol=1e-12) for row in rows))
