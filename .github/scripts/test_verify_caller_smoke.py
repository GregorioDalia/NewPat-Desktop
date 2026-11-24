import csv
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import verify_caller_smoke as smoke


class CallerSmokeTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)
        self.steps = []
        for marker in ("dnp", "snp"):
            tables = []
            for sample, genotype in (("mother", "0/0"), ("father", "0/1"), ("child", "0/1")):
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

    def test_examples_tables_cannot_change_the_oracle(self):
        example = self.root / "synthetic-trio"
        shutil.copytree(smoke.TRIO / "counts", example / "counts")
        # A bug alters both the packaged example counts and the candidate table.
        for path in (example / "counts/dnp/mother.txt", self.root / "dnp-mother.tsv"):
            rows = smoke.read_table(path)
            for row in rows:
                row["N_REF"] = "95"
                row["N_ALT"] = "5"
            self.write_table(path, rows)
        with patch.object(smoke, "TRIO", example), self.assertRaisesRegex(ValueError, "DNP mother"):
            self.check()

    def test_rejects_coordinates_alleles_totals_and_other_counts(self):
        path = self.root / "dnp-mother.tsv"
        rows = smoke.read_table(path)
        for field, replacement in (("chr", "chr2"), ("pos1", "220"), ("pos2", "239"),
                                   ("REF", "AA"), ("ALT", "TT"), ("N_Other", "2"), ("total_count", "99")):
            with self.subTest(field=field):
                self.write_table(path, [{**rows[0], field: replacement}, *rows[1:]])
                with self.assertRaisesRegex(ValueError, "DNP mother"):
                    self.check()

    def test_rejects_the_same_output_table_under_distinct_sample_labels(self):
        father, child = (step["artifacts"]["snp-tables"][0] for step in self.steps[-2:])
        child["path"] = father["path"]
        with self.assertRaisesRegex(ValueError, "own table"):
            self.check()

    def test_pins_every_planned_input_and_rejects_a_changed_sample_assignment(self):
        example = self.root / "synthetic-trio"
        # Only the two panels, reference, BAMs and companion indexes are needed.
        for name in ("reference", "alignments", "panels"):
            shutil.copytree(smoke.TRIO / name, example / name)
        layout = smoke.ProjectLayout(smoke.ROOT, self.root, self.root / "data", self.root / "runs",
                                     smoke.ROOT / "compose.yaml")
        with patch.object(smoke, "TRIO", example):
            prepared = smoke.prepare(layout)
            smoke.check_inputs(prepared)
            self.assertEqual(len(prepared.evidence), 10)
            for path, _ in prepared.evidence:
                with self.subTest(path=path.name):
                    source = path.read_bytes()
                    path.write_bytes(source + b"x")
                    with self.assertRaisesRegex(ValueError, "Synthetic trio input changed"):
                        smoke.check_inputs(prepared)
                    path.write_bytes(source)
            mother, father, child = prepared.inputs["samples"]
            prepared.inputs["samples"] = [mother, (father[0], child[1]), (child[0], father[1])]
            with self.assertRaisesRegex(ValueError, "wrong sample"):
                smoke.check_inputs(prepared)

    def test_rejects_results_attributed_twice_to_the_same_sample(self):
        # Father and child have identical counts in this fixture. Their presence
        # must also be checked by sample identity.
        self.steps[-1]["artifacts"]["snp-tables"][0]["sample"] = "father"
        with self.assertRaisesRegex(ValueError, "one DNP and one SNP table per sample"):
            self.check()


if __name__ == "__main__":
    unittest.main()
