"""Site eligibility and obligate paternal allele in the current postnatal output."""

from itertools import product
from pathlib import Path
import tempfile
import unittest

import test_native_r_edge_cases as native
from downstream_oracle_tables import alleles, coordinate, coordinate_header, write_calls, write_table
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON


@unittest.skipUnless(NATIVE_R_AVAILABLE, NATIVE_R_REASON)
class PostnatalTrioContract(unittest.TestCase):
    def test_all_27_genotype_combinations(self):
        # A homozygous mother supplies exactly one known maternal allele. For a
        # compatible child the other allele is obligatory, regardless of father.
        required = {
            ("0/0", "0/0"): "REF", ("0/0", "0/1"): "ALT",
            ("1/1", "0/1"): "REF", ("1/1", "1/1"): "ALT",
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
                            ((*row, .75, .25) for row in reversed(markers)))
                proc, output = native.NativeREdgeCases.run_native(
                    self, root, "cpin", inputs, ("--markers", str(inputs / "panel.tsv")))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                sites = native.table(output / f"sites/MotherM1-FatherF1-ChildC1_{marker}s_sites.tsv")
                pos = "pos" if marker == "SNP" else "pos1"
                observed = {int(site[pos]): site for site in sites}
                self.assertEqual(len(sites), len(trios))
                self.assertEqual(set(observed), {coordinate(marker, i)[1] for i, _ in trios})
                for locus, (mother, father, child) in trios:
                    with self.subTest(mother=mother, father=father, child=child):
                        site = observed[coordinate(marker, locus)[1]]
                        self.assertEqual(site["chr"], coordinate(marker, locus)[0])
                        self.assertEqual((site["GT_mother"], site["GT_father"], site["GT_child"]),
                                         (mother, father, child))
                        allele = required.get((mother, child))
                        self.assertEqual(site["Required_paternal_allele"], allele or "NA")
                        if allele is None:
                            status = "mother_not_homozygous" if mother == "0/1" else "mother_child_incompatible"
                            self.assertEqual(site["Status"], status)
                            self.assertEqual(site["Paternity_Index"], "NA")
                            continue
                        self.assertEqual(site["Status"], "eligible")
                        transmission = father.count("0" if allele == "REF" else "1") / 2
                        self.assertEqual(float(site["Paternal_transmission"]), transmission)
                        self.assertEqual(site["Mismatch"], "TRUE" if transmission == 0 else "FALSE")
                summary = native.table(output / "Summary_Postnatal_CPI.txt")
                self.assertEqual(
                    {row["Analysis"]: (int(row["N_sites"]), int(row["Matching_sites"]), int(row["Mismatching_sites"]))
                     for row in summary},
                    {"heterozygous_child_sites": (6, 4, 2), "all_compatible_sites": (12, 8, 4)},
                )
