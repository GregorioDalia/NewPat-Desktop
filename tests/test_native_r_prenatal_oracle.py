"""Independent rational-product oracles for both marker types and every fetal-support threshold."""

import csv
from fractions import Fraction
import math
from pathlib import Path
import statistics
import tempfile
import unittest

import test_native_r_edge_cases as native
from downstream_oracle_tables import alleles, coordinate, coordinate_header, write_calls, write_table
from native_engine_helpers import execute_workflow
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
                non_mismatch = sum(site[3] == "match" for site in selected)
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

    def test_independent_absolute_percentage_and_combined_filters_through_engine(self):
        # Maternal minor allele supports and percentages are (1,10%), (2,2%),
        # (5,5%), (4,2%). Locus 3 has ten Other reads, which must be excluded
        # from the percentage denominator. Each matching father has a distinct PI.
        profiles = (
            ({}, "2", "NA", 3, {2: 200, 3: 50, 4: 50, 5: 5}),
            ({"min_fetal_reads": 4}, "4", "NA", 2, {4: 50, 5: 5}),
            ({"min_fetal_percent": 5}, "NA", "5", 2, {1: 10, 2: 5, 3: 5, 4: 5, 5: 5}),
            ({"min_fetal_reads": 2, "min_fetal_percent": 5}, "2", "5", 1, {2: 5, 3: 5, 4: 5, 5: 5}),
            ({"min_fetal_percent": 100}, "NA", "100", 0, {}),
        )
        for marker in ("SNP", "DNP"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                mother, father = root / "MotherM1.txt", root / "FatherF1.txt"
                write_calls(mother, marker, [(1, (9, 1, 0)), (2, (2, 98, 0)), (3, (95, 5, 10)), (4, (196, 4, 0))])
                write_calls(father, marker, [(4, (0, 10, 0)), (3, (0, 10, 0)), (2, (10, 0, 0)), (1, (0, 10, 0))])
                frequencies = root / "population.txt"
                rows = [(*coordinate(marker, locus), *alleles(marker), ref, alt)
                        for locus, ref, alt in ((1, .5, .5), (2, .25, .75), (3, .8, .2), (4, .9, .1))]
                write_table(frequencies, (*coordinate_header(marker), "REF", "ALT", "Ref_f.pop", "Alt_f.pop"), rows)
                for index, (settings, reads, percent, count, curve) in enumerate(profiles):
                    with self.subTest(marker=marker, settings=settings):
                        run = root / f"run_{index}"
                        result = execute_workflow(
                            "cpi", run, marker_type=marker,
                            samples=[{"path": str(p), "name": p.name} for p in (mother, father)],
                            pairs="M1:F1", mother_prefix="Mother", father_prefix="Father",
                            popfreq=str(frequencies), cutoff_mode="all", cutoffs=[], scientific_settings=settings)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        output = run / "output"
                        summary, = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
                        self.assertEqual((summary["Min_fetal_reads"], summary["Min_fetal_percent"]), (reads, percent))
                        self.assertEqual((int(summary["N_sites_mother"]), int(summary["N_sites_father"])), (count, count))
                        points = native.table(next((output / "curves").glob("*.tsv")))
                        self.assertEqual([int(p["Iteration"]) for p in points], list(curve))
                        for point in points:
                            expected = curve[int(point["Iteration"])]
                            self.assertAlmostEqual(float(point["CPI"]), expected)
                            self.assertAlmostEqual(float(point["log_CPI"]), math.log10(expected))
                        if not count:
                            self.assertEqual(summary["CPI_medianFF"], "NA")

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

    def test_maximum_absolute_filter_accepts_r_integer_limit(self):
        maximum = 2**31 - 1
        for support in (maximum - 1, maximum):
            with self.subTest(support=support), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                mother, father, frequencies = (root / name for name in ("MotherM1.txt", "FatherF1.txt", "pop.tsv"))
                write_calls(mother, "SNP", [(1, (10 * maximum, support, 0))])
                write_calls(father, "SNP", [(1, (0, 20, 0))])
                write_table(frequencies, (*coordinate_header("SNP"), "Ref_f.pop", "Alt_f.pop"),
                            [(*coordinate("SNP", 1), .8, .2)])
                run = root / "run"
                result = execute_workflow("cpi", run, marker_type="SNP",
                    samples=[{"path": str(p), "name": p.name} for p in (mother, father)],
                    pairs="M1:F1", mother_prefix="Mother", father_prefix="Father", popfreq=str(frequencies),
                    cutoff_mode="all", cutoffs=[], scientific_settings={"min_fetal_reads": maximum})
                self.assertEqual(result.returncode, 0, result.stderr)
                output = run / "output"
                summary, = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
                self.assertEqual(int(summary["Min_fetal_reads"]), maximum)
                self.assertEqual(int(summary["N_sites_mother"]), int(support == maximum))
                curve = native.table(next((output / "curves").glob("*.tsv")))
                self.assertEqual([int(p["Iteration"]) for p in curve], [maximum] if support == maximum else [])
                if curve:
                    self.assertAlmostEqual(float(curve[0]["CPI"]), 5)
                else:
                    self.assertEqual(summary["CPI_medianFF"], "NA")

    def assert_published_table(self, expected, actual, delimiter, *, allow_extra=False):
        with expected.open(encoding="utf-8", newline="") as reference, actual.open(encoding="utf-8", newline="") as result:
            oracle = csv.DictReader(reference, delimiter=delimiter)
            observed = csv.DictReader(result, delimiter=delimiter)
            if allow_extra:
                self.assertTrue(set(oracle.fieldnames).issubset(observed.fieldnames), actual.name)
            else:
                self.assertEqual(set(oracle.fieldnames), set(observed.fieldnames), actual.name)
            for index, (want, got) in enumerate(zip(oracle, observed, strict=True), start=1):
                for column in oracle.fieldnames:
                    message = f"{actual.name}, row {index}, {column}"
                    try:
                        numeric = float(want[column])
                    except ValueError:
                        self.assertEqual(got[column], want[column], message)
                    else:
                        self.assertTrue(math.isclose(float(got[column]), numeric, rel_tol=2e-12, abs_tol=0),
                                        f"{message}: {got[column]} vs {want[column]}")

    def test_published_twenty_marker_tables(self):
        fixture = native.ROOT / "tests/fixtures/prenatal_cpi"
        for marker in ("DNP", "SNP"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                inputs = fixture / "inputs" / marker
                expected = fixture / "outputs" / marker
                run = Path(temp) / "run"
                result = execute_workflow(
                    "cpi", run, marker_type=marker, execution_mode="auto",
                    samples=[{"path": str(inputs / name), "name": name} for name in ("MotherA1.txt", "FatherA1.txt")],
                    pairs="A1:A1", mother_prefix="Mother", father_prefix="Father",
                    popfreq=str(inputs / "population_frequencies.txt"), cutoff_mode="panel",
                    cutoffs=[{"label": "", "path": str(inputs / "markers.txt")}])
                self.assertEqual(result.returncode, 0, result.stderr)
                output = run / "output"
                pair = f"MotherA1-FatherA1_{marker}s"
                for file, delimiter in (("Summary_FetalFraction_CPI.csv", ","),
                                        (pair + "_CPI_iterations.csv", ","), (pair + "_HOM_child_sites.txt", "\t")):
                    self.assert_published_table(expected / file, output / file, delimiter,
                                                allow_extra=file == "Summary_FetalFraction_CPI.csv")
                for name in (pair + "_CPIplot.pdf", "All_CPIplots.pdf"):
                    self.assertTrue((output / "plots" / name).read_bytes().startswith(b"%PDF-"))

    def test_hom_child_sites_coverage_other_and_median_support(self):
        # A HET support of 4 has PI 5. The HET site with support 6 has an
        # unassigned father. Therefore there is no HET contribution at threshold 5.
        # The two permitted HOM sites give PI 2 and .001/.25. By construction
        # site 4 is exactly at both depth and Other-fraction limits.
        for marker in ("DNP", "SNP"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                mother, father = root / "MotherM1.txt", root / "FatherF1.txt"
                m = [(96, 4, 0), (94, 6, 0), (10, 0, 0), (0, 9, 1), (9, 0, 0), (10, 0, 0),
                     (8, 0, 2), (10, 0, 0)]
                f = [(0, 10, 0), (7, 3, 0), (9, 1, 0), (10, 0, 0), (10, 0, 0), (9, 0, 0),
                     (10, 0, 0), (8, 0, 2)]
                frequencies = [(.8, .2), (.5, .5), (.5, .5), (.75, .25)] + [(.5, .5)] * 4
                write_calls(mother, marker, list(enumerate(m, 1)))
                write_calls(father, marker, list(enumerate(f, 1)))
                pop = root / "pop.tsv"
                write_table(pop, (*coordinate_header(marker), "Ref_f.pop", "Alt_f.pop"),
                            ((*coordinate(marker, i), *freq) for i, freq in enumerate(frequencies, 1)))
                for index, (enabled, other_max, hom_ids) in enumerate((
                    (False, .1, []), (True, .1, [3, 4]), (True, .2, [3, 4, 7, 8]),
                )):
                    with self.subTest(enabled=enabled, max_other=other_max):
                        run = root / f"run_{index}"
                        settings = {"include_homozygous_child": enabled, "min_coverage": 10,
                                    "other_fraction_max": other_max, f"err_const_{marker.lower()}": .001}
                        result = execute_workflow(
                            "cpi", run, marker_type=marker, samples=[{"path": str(p), "name": p.name} for p in (mother, father)],
                            pairs="M1:F1", mother_prefix="Mother", father_prefix="Father",
                            popfreq=str(pop), cutoff_mode="all", cutoffs=[], scientific_settings=settings)
                        self.assertEqual(result.returncode, 0, result.stderr)
                        output = run / "output"
                        summary, = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
                        self.assertEqual(summary["Include_homozygous_child"], str(enabled).upper())
                        self.assertEqual(summary["Min_coverage"], "10")
                        self.assertEqual(float(summary["Max_other_fraction"]), other_max)
                        self.assertEqual(float(summary["Median_fetal_fraction_percent"]), 10)
                        self.assertEqual(summary["N_sites_HET_child"], "0")
                        self.assertEqual(int(summary["N_sites_HOM_child"]), len(hom_ids))
                        hom = native.table(next(output.glob("*_HOM_child_sites.txt")))
                        key = "pos" if marker == "SNP" else "pos1"
                        by_locus = {int(h[key]) // 10: h for h in hom}
                        self.assertEqual(len(hom), len(hom_ids))
                        self.assertEqual(set(by_locus), set(hom_ids))
                        for locus in hom_ids:
                            h = by_locus[locus]
                            self.assertEqual(h["Mismatch"], "TRUE" if locus == 4 else "FALSE")
                            self.assertAlmostEqual(float(h["Paternity_Index"]), .004 if locus == 4 else 2)
                        hom_pi = math.prod(.004 if locus == 4 else 2 for locus in hom_ids)
                        if hom_ids:
                            self.assertAlmostEqual(float(summary["CPI_medianFF"]), round(math.log10(hom_pi), 3))
                        else:
                            self.assertEqual(summary["CPI_medianFF"], "NA")
                        rows = native.table(next(output.glob("*_CPI_iterations.csv")), ",")
                        self.assertEqual([int(r["Iteration"]) for r in rows], [2, 3, 4, 5, 6])
                        for row in rows:
                            het_match = int(int(row["Iteration"]) <= 4)
                            self.assertEqual(int(row["NotMismatch"]), het_match + len(hom_ids) - int(enabled))
                            self.assertEqual(int(row["Mismatch"]), int(enabled))
                            self.assertEqual(int(row["InfSites_father"]), het_match + len(hom_ids))
                            self.assertAlmostEqual(float(row["Log10_CPI_HOM_child"]), math.log10(hom_pi))
                            if het_match or hom_ids:
                                self.assertAlmostEqual(float(row["CPI"]), (5 if het_match else 1) * hom_pi)
                            else:
                                self.assertEqual(row["CPI"], "NA")

    def test_hom_only_panel_keeps_site_audit_without_a_median_fetal_fraction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mother, father, population = (root / name for name in ("MotherM.txt", "FatherF.txt", "freq.tsv"))
            write_calls(mother, "SNP", [(1, (96, 4, 0)), (2, (20, 0, 0))])
            write_calls(father, "SNP", [(1, (0, 20, 0)), (2, (20, 0, 0))])
            markers = [coordinate("SNP", locus) for locus in (1, 2)]
            write_table(population, ("chr", "pos", "Ref_f.pop", "Alt_f.pop"), [(*m, .75, .25) for m in markers])
            cutoffs = []
            for label, site in zip(("het", "hom"), markers, strict=True):
                panel = root / f"{label}.tsv"
                write_table(panel, ("chr", "pos", "REF", "ALT"), [(*site, "A", "T")])
                cutoffs.append({"label": label, "path": str(panel)})
            run = root / "run"
            result = execute_workflow(
                "cpi", run, marker_type="SNP", execution_mode="auto",
                samples=[{"path": str(p), "name": p.name} for p in (mother, father)],
                pairs="M:F", mother_prefix="Mother", father_prefix="Father", popfreq=str(population),
                cutoff_mode="named", cutoffs=cutoffs, scientific_settings={"include_homozygous_child": True})
            self.assertEqual(result.returncode, 0, result.stderr)
            output = run / "output"
            het, hom = native.table(output / "Summary_FetalFraction_CPI.csv", ",")
            self.assertEqual((het["Cutoff"], hom["Cutoff"]), ("het", "hom"))
            self.assertEqual((het["N_sites_HET_child"], het["N_sites_HOM_child"]), ("1", "0"))
            self.assertEqual((hom["N_sites_HET_child"], hom["N_sites_HOM_child"]), ("0", "1"))
            for column in ("Median_fetal_fraction_raw", "CPI_medianFF", "Log10_CPI_HET_child"):
                self.assertEqual(hom[column], "NA", column)
            self.assertAlmostEqual(float(hom["Log10_CPI_HOM_child"]), round(math.log10(4 / 3), 3))
            self.assertEqual(native.table(output / "MotherM-FatherF_SNPs_panel_2_CPI_iterations.csv", ","), [])
            self.assertEqual(native.table(output / "MotherM-FatherF_SNPs_panel_1_HOM_child_sites.txt"), [])
            only_site, = native.table(output / "MotherM-FatherF_SNPs_panel_2_HOM_child_sites.txt")
            self.assertEqual((only_site["pos"], only_site["Mismatch"]), ("20", "FALSE"))
            self.assertAlmostEqual(float(only_site["Paternity_Index"]), 4 / 3)
