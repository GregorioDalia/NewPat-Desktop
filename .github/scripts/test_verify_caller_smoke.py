import csv
import json
from pathlib import Path
import tempfile
import unittest

import verify_caller_smoke as smoke


class CallerSmokeTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.steps = []
        for marker in ("dnp", "snp"):
            tables = []
            for sample, genotype in smoke.GENOTYPES.items():
                rows = smoke.read_table(smoke.TRIO / "counts" / marker / f"{sample}.txt")
                for row in rows:
                    row["GT"] = genotype
                path = self.root / f"{marker}-{sample}.tsv"
                self.write_table(path, rows[::-1])
                tables.append({"sample": sample, "path": path.name})
            for group in ([tables] if marker == "dnp" else [[table] for table in tables]):
                self.steps.append({"status": "succeeded", "workflow": f"{marker}-call",
                                   "artifacts": {f"{marker}-tables": group}})

    @staticmethod
    def write_table(path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, delimiter="\t", fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    def check(self):
        (self.root / "workflow-state.json").write_text(
            json.dumps({"status": "succeeded", "steps": self.steps}), encoding="utf-8")
        smoke.check_results(self.root)

    def test_accepts_matching_loci_in_any_order(self):
        self.check()

    def test_rejects_wrong_counts_and_genotype_and_missing_or_duplicated_loci(self):
        for marker in ("dnp", "snp"):
            path = self.root / f"{marker}-mother.tsv"
            rows = smoke.read_table(path)
            for mutation in ([{**rows[0], "N_REF": "4"}, *rows[1:]],
                             [{**rows[0], "GT": "0/1"}, *rows[1:]], rows[1:],
                             [rows[1], *rows[1:]]):
                with self.subTest(marker=marker, mutation=mutation[0]):
                    self.write_table(path, mutation)
                    with self.assertRaisesRegex(ValueError, f"{marker.upper()} mother"):
                        self.check()
            self.write_table(path, rows)

    def test_rejects_results_attributed_twice_to_the_same_sample(self):
        # Father and child have identical counts in this fixture. Their presence
        # must also be checked by sample identity.
        self.steps[-1]["artifacts"]["snp-tables"][0]["sample"] = "father"
        with self.assertRaisesRegex(ValueError, "one DNP and one SNP table per sample"):
            self.check()


if __name__ == "__main__":
    unittest.main()
