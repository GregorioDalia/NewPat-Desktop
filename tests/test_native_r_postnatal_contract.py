"""Site eligibility and obligate paternal allele in the current postnatal output."""

from itertools import product
import math
from pathlib import Path
import tempfile
import unittest

import test_native_r_edge_cases as native
from downstream_oracle_tables import alleles, coordinate, coordinate_header, write_calls, write_table
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class PostnatalTrioContract(unittest.TestCase):
    def test_all_27_genotype_combinations(self):
        # Mother/child inheritance determines the obligate allele independently of the father.
        required = {
            ("0/0", "0/0"): "REF", ("0/0", "0/1"): "ALT",
            ("1/1", "0/1"): "REF", ("1/1", "1/1"): "ALT",
            ("0/1", "0/0"): "REF", ("0/1", "1/1"): "ALT",
        }
        counts = {"0/0": (100, 0, 0), "0/1": (50, 50, 0), "1/1": (0, 100, 0)}
        trios = list(enumerate(product(counts, repeat=3), start=1))
        for marker in ("SNP", "DNP"):
            with self.subTest(marker=marker), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                inputs = root / "inputs"
                inputs.mkdir()
                for role, filename in enumerate(("MotherM1", "FatherF1", "ChildC1")):
                    source = reversed(trios) if role == 1 else trios
                    write_calls(inputs / f"{filename}.txt", marker,
                                [(index, counts[genotypes[role]]) for index, genotypes in source])
                head = (*coordinate_header(marker), "REF", "ALT")
                markers = [(*coordinate(marker, locus), *alleles(marker)) for locus, _ in trios]
                write_table(inputs / "panel.tsv", head if marker == "SNP" else None, markers)
                write_table(inputs / "population.txt", (*head, "Ref_f.pop", "Alt_f.pop"),
                            ((*row, .5, .25) for row in reversed(markers)))
                proc, output = native.NativeREdgeCases.run_native(
                    self, root, "cpin", inputs, ("--markers", str(inputs / "panel.tsv")))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                sites = native.table(output / f"MotherM1-FatherF1-ChildC1_{marker}s_sites.txt")
                pos = "pos" if marker == "SNP" else "pos1"
                observed = {int(site[pos]): site for site in sites}
                self.assertEqual(len(sites), len(trios))
                self.assertEqual(set(observed), {coordinate(marker, i)[1] for i, _ in trios})
                # Deliberately non-unit frequency sum checks the general het/het formula.
                epsilon = .001 if marker == "SNP" else .0000892303778101497
                factors = []
                for locus, (mother, father, child) in trios:
                    with self.subTest(mother=mother, father=father, child=child):
                        site = observed[coordinate(marker, locus)[1]]
                        self.assertEqual(site["chr"], coordinate(marker, locus)[0])
                        self.assertEqual((site["GT_mother"], site["GT_father"], site["GT_child"]),
                                         (mother, father, child))
                        allele = required.get((mother, child))
                        self.assertEqual(site["Required_paternal_allele"], allele or "NA")
                        if mother == child == "0/1":
                            self.assertEqual(site["Genotype_combination"], "het_het")
                            self.assertEqual(site["Status"], "eligible")
                            self.assertEqual(site["Paternity_status"], "no_obligatory_allele")
                            self.assertEqual((site["Mismatch"], site["Paternal_transmission"]), ("NA", "NA"))
                            self.assertAlmostEqual(float(site["Paternity_Index"]), 4 / 3)
                            factors.append(4 / 3)
                            continue
                        if allele is None:
                            self.assertEqual(site["Status"], "mother_child_incompatible")
                            self.assertEqual(site["Paternity_Index"], "NA")
                            self.assertEqual(site["Paternity_status"], "NA")
                            continue
                        self.assertEqual(site["Status"], "eligible")
                        transmission = father.count("0" if allele == "REF" else "1") / 2
                        self.assertEqual(float(site["Paternal_transmission"]), transmission)
                        self.assertEqual(site["Mismatch"], "TRUE" if transmission == 0 else "FALSE")
                        self.assertEqual(site["Paternity_status"], "mismatch" if transmission == 0 else "match")
                        frequency = .5 if allele == "REF" else .25
                        factor = (transmission or epsilon) / frequency
                        self.assertAlmostEqual(float(site["Paternity_Index"]), factor)
                        factors.append(factor)
                summary, = native.table(output / "Summary_Postnatal_CPI.txt")
                for column, count in {
                    "N_sites": 21, "Matching_sites": 12, "Mismatching_sites": 6,
                    "N_hom_hom": 6, "N_hom_het": 6, "N_het_hom": 6, "N_het_het": 3,
                    "No_obligatory_allele_sites": 3, "Maternal_incompatible_sites": 6,
                }.items():
                    self.assertEqual(int(summary[column]), count, column)
                self.assertTrue(math.isclose(float(summary["CPI"]), math.prod(factors), rel_tol=1e-12))
                self.assertAlmostEqual(float(summary["Log10_CPI"]), math.log10(math.prod(factors)))

                restricted = root / "restricted"
                restricted.mkdir()
                proc, output = native.NativeREdgeCases.run_native(
                    self, restricted, "cpin", inputs, settings={"include_het_hom": False})
                self.assertEqual(proc.returncode, 0, proc.stderr)
                row, = native.table(output / "Summary_Postnatal_CPI.txt")
                self.assertEqual((row["N_sites"], row["N_het_hom"]), ("15", "0"))
                sites = native.table(next(output.glob("*_sites.txt")))
                disabled = [s for s in sites if s["Status"] == "combination_not_selected"]
                self.assertEqual(len(disabled), 6)
                self.assertTrue(all(s["Genotype_combination"] == "het_hom" and s["Paternity_Index"] == "NA"
                                    for s in disabled))
