"""Check the packaged prenatal CPI summary and staged marker panels."""

import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from newpat_scientific.panels import read_position_panel, write_position_panel


PROJECT = Path(__file__).resolve().parents[1]


class CpiPackageStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "newpat_cpi_package_staging", PROJECT / "scripts/verify_cpi_engine.py")
        cls.helper = importlib.util.module_from_spec(spec)
        with patch.object(sys, "path", [str(PROJECT / "scripts"), *sys.path]):
            spec.loader.exec_module(cls.helper)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="newpat CPI staging gate ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "work/inputs").mkdir(parents=True)
        self.panel = self.root / "work/DNPpanel.txt"

    def check(self, *, include_alleles):
        self.helper.check_staging(self.root, {}, {"DNPpanel.txt": ((100, 200), include_alleles)})

    def test_default_summary_records_inactive_percent_filter_with_and_without_a_panel(self):
        pair = "MotherM-FatherF_DNPs"
        plots = self.root / "output/plots"
        plots.mkdir(parents=True)
        for name in ("All_CPIplots.pdf", f"{pair}_CPIplot.pdf"):
            (plots / name).write_bytes(b"%PDF-")
        summary = self.root / "output/Summary_FetalFraction_CPI.csv"
        for panel in (None, "Full"):
            expected = {(pair, panel): self.helper.NO_SITES}
            for percentage in ("NA", "0", None):
                with self.subTest(panel=panel, percentage=percentage):
                    row = {"Pair": pair, **self.helper.NO_SITES, "Marker_type": "DNP",
                           "Error_constant": self.helper.DEFAULT_ERR_CONST, "Min_fetal_reads": 2,
                           "Include_homozygous_child": "FALSE", "Min_coverage": "NA", "Max_other_fraction": 0.1,
                           "N_sites_HET_child": 0, "N_sites_HOM_child": 0, "Matching_HET_child": 0,
                           "Mismatching_HET_child": 0, "Matching_HOM_child": 0, "Mismatching_HOM_child": 0,
                           "Log10_CPI_HET_child": "NA", "Log10_CPI_HOM_child": 0}
                    if panel is not None:
                        row["Cutoff"] = panel
                    if percentage is not None:
                        row["Min_fetal_percent"] = percentage
                    with summary.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=row)
                        writer.writeheader()
                        writer.writerow(row)
                    if percentage == "NA":
                        self.helper.check_summary(self.root, expected)
                    else:
                        with self.assertRaisesRegex(ValueError, "columns|Min_fetal_percent"):
                            self.helper.check_summary(self.root, expected)

    def test_allele_bearing_output_preserves_schema_coordinates_and_alleles(self):
        records = read_position_panel(PROJECT / "tests/fixtures/cpi/DNP_list.txt")[:2]
        write_position_panel(records, self.panel)
        self.check(include_alleles=True)
        original = self.panel.read_text(encoding="utf-8")
        for mutated in (
            # Losing alleles must fail even when coordinates remain correct.
            "n°DNP\tchr\tpos1\tpos2\nDNP001\tchr1\t100\t101\nDNP002\tchr1\t200\t201\n",
            original.replace("AA\tCC", "AA\tTT"),
            original.replace("100\t101", "100\t102"),
            original.replace("REF\tALT", "ALT\tREF"),
            original.replace("chr\tpos1", "chromosome\tpos1"),
        ):
            with self.subTest(panel=mutated):
                self.panel.write_text(mutated, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "expected coordinates or alleles"):
                    self.check(include_alleles=True)

    def test_coordinate_only_output_preserves_ids_without_inventing_alleles(self):
        source = self.root / "positions.tsv"
        source.write_text("chr\tpos1\tpos2\nchr1\t100\t101\nchr1\t200\t201\n", encoding="utf-8")
        write_position_panel(read_position_panel(source), self.panel)
        self.check(include_alleles=False)
        original = self.panel.read_text(encoding="utf-8")
        for mutated in (
            original.replace("DNP002", "DNP003"),
            original.replace("200\t201", "200\t202"),
            "chr\tpos1\tpos2\tREF\tALT\nchr1\t100\t101\tAA\tCC\nchr1\t200\t201\tGG\tTT\n",
        ):
            with self.subTest(panel=mutated):
                self.panel.write_text(mutated, encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "expected coordinates or alleles"):
                    self.check(include_alleles=False)


if __name__ == "__main__":
    unittest.main()
