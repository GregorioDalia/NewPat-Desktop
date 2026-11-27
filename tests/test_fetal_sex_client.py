"""Verify the file identities, region assignments and settings handed to the engine."""
import json
from pathlib import Path
import tempfile
import unittest

from newpat.cli import build_parser
from newpat.errors import ValidationError
from newpat.experiments.workflows import Workflows
from newpat.paths import ProjectLayout
from test_workflow_client import RecordingRunner


class FetalSexClientTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.layout = ProjectLayout(root / "app", root, root / "data", root / "runs", root / "compose.yaml")
        self.runner = RecordingRunner()
        self.workflows = Workflows(self.layout, self.runner,
                                   scientific_settings={"fetal-sex": {"min_fetal_percent": 4.5}})
        fixtures = Path(__file__).parent / "fixtures" / "fetal_sex" / "inputs"
        self.paths = {role: fixtures / f"Male_fetus_{name}.txt" for role, name in
                      (("autosomes", "autosomes"), ("x", "X"), ("y", "Y"))}

    def test_standalone_preserves_original_sample_name_and_read_only_mounts(self):
        args = build_parser().parse_args(["fetal-sex", "--autosomes", str(self.paths["autosomes"]),
                                          "--X", str(self.paths["x"]), "--Y", str(self.paths["y"])])
        run = self.workflows.fetal_sex(autosomes=args.autosomes, x=args.x, y=args.y)
        request = json.loads((run / "work" / "engine-request.json").read_text())
        record = self.runner.records[0][1]
        self.assertEqual(record["bundled_workflow"], "fetal-sex")
        self.assertEqual(request["workflow"], "fetal-sex")
        self.assertEqual(request["scientific_settings"], {"min_fetal_percent": 4.5})
        mounts = {m["container_path"]: m for m in record["mounts"].mappings}
        for role, source in self.paths.items():
            self.assertEqual(mounts[request[role]]["host_path"], str(source.resolve()))
            self.assertTrue(mounts[request[role]]["read_only"])
            self.assertEqual(Path(request[role]).name, source.name)
            self.assertEqual(record["parameters"]["fetal_sex"][role], str(source.resolve()))

    def test_plan_provides_three_roles_for_one_biological_identity(self):
        run = self.workflows.analyze(caller="tables", analyses=[],
                                     fetal_sex=("Mother", *self.paths.values()))
        metadata = self.runner.records[0][1]["parameters"]
        self.assertEqual(metadata["fetal_sex"]["sample_id"], "Mother")
        self.assertEqual({item["biological_id"] for item in metadata["sample_mapping"]}, {"Mother"})
        plan = json.loads((run / "work" / "engine-plan.json").read_text())
        step, = plan["steps"]
        self.assertEqual(step["inputs"], {"autosomes": "fsa_Mother", "x": "fsx_Mother", "y": "fsy_Mother"})
        self.assertEqual(step["parameters"]["scientific_settings"]["min_fetal_percent"], 4.5)
        self.assertEqual({s["id"]: s["kind"] for s in plan["samples"]},
                         {"fsa_Mother": "dnp-table", "fsx_Mother": "dnp-table", "fsy_Mother": "snp-table"})

    def combined_table(self):
        dnp = self.layout.workspace_dir / "full_output_Mother.txt"
        dnp.write_bytes(self.paths["autosomes"].read_bytes() +
                        self.paths["x"].read_bytes().split(b"\n", 1)[1])
        return dnp

    def test_combined_inputs_retain_the_original_paths_in_standalone_and_plan(self):
        dnp = self.combined_table()
        y = self.paths["y"]
        parser = build_parser()
        args = parser.parse_args(["fetal-sex", "--dnp", str(dnp), "--Y", str(y)])
        standalone = self.workflows.fetal_sex(dnp=args.dnp, y=args.y)
        request = json.loads((standalone / "work/engine-request.json").read_text())
        self.assertEqual(Path(request["dnp"]).name, dnp.name)
        self.assertEqual(Path(request["y"]).name, y.name)
        self.assertTrue({"autosomes", "x"}.isdisjoint(request))
        record = self.runner.records[-1][1]
        sources = {"dnp": str(dnp.resolve()), "y": str(y.resolve())}
        self.assertEqual(record["parameters"]["fetal_sex"],
                         {"sample_id": dnp.stem, **sources})
        self.assertEqual({(m["host_path"], m["read_only"]) for m in record["mounts"].mappings},
                         {(path, True) for path in sources.values()})

        args = parser.parse_args(["workflow", "analyze", "--caller", "tables",
                                  "--fetal-sex", "Mother", str(dnp), str(y)])
        run = self.workflows.analyze(caller=args.caller, analyses=[], fetal_sex=args.fetal_sex)
        plan = json.loads((run / "work/engine-plan.json").read_text())
        step, = plan["steps"]
        self.assertEqual(step["inputs"], {"dnp": "fsd_Mother", "y": "fsy_Mother"})
        self.assertEqual({s["id"]: s["kind"] for s in plan["samples"]},
                         {"fsd_Mother": "dnp-table", "fsy_Mother": "snp-table"})
        self.assertEqual(self.runner.records[-1][1]["parameters"]["fetal_sex"],
                         {"sample_id": "Mother", **sources})

    def test_mixed_workflow_reuses_the_combined_maternal_count_table(self):
        dnp = self.combined_table()
        panel = self.layout.workspace_dir / "sites.tsv"
        panel.write_text("chr\tpos1\tpos2\nchr1\t3010000\t3010001\n", encoding="utf-8")
        run = self.workflows.analyze(caller="tables", analyses=["contamination"],
                                     dnp_tables=[("Mother", dnp)], dnp_contamination_panel=panel,
                                     fetal_sex=("Mother", dnp, self.paths["y"]))
        plan = json.loads((run / "work/engine-plan.json").read_text())
        self.assertEqual(len(plan["samples"]), 2)
        contamination, sex = plan["steps"]
        self.assertEqual(contamination["inputs"]["samples"], [{"sample": "dnp_Mother"}])
        self.assertEqual(sex["inputs"], {"dnp": "dnp_Mother", "y": "fsy_Mother"})
        mounts = self.runner.records[-1][1]["mounts"].mappings
        self.assertEqual(sum(m["host_path"] == str(dnp.resolve()) for m in mounts), 1)

    def test_incomplete_or_mixed_table_layouts_are_rejected_before_recording(self):
        for tables in ({"autosomes": self.paths["autosomes"]},
                       {"dnp": self.paths["autosomes"], "x": self.paths["x"]}):
            with self.subTest(tables=tables), self.assertRaises(ValidationError):
                self.workflows.fetal_sex(y=self.paths["y"], **tables)
        self.assertFalse(self.layout.runs_dir.exists())
        self.assertFalse(self.runner.calls)

    def test_shared_autosomal_import_retains_one_identity_and_one_read_only_mount(self):
        panel = self.layout.workspace_dir / "positions.tsv"
        panel.write_text("chr\tpos1\tpos2\nchr1\t10\t11\n", encoding="utf-8")
        options = dict(caller="tables", analyses=["contamination"], dnp_contamination_panel=panel,
                       fetal_sex=("Mother", *self.paths.values()))
        with self.assertRaisesRegex(ValidationError, "stesso ID"):
            self.workflows.analyze(dnp_tables=[("Other", self.paths["autosomes"])], **options)
        self.assertFalse(self.layout.runs_dir.exists())
        run = self.workflows.analyze(dnp_tables=[("Mother", self.paths["autosomes"])], **options)
        plan = json.loads((run / "work/engine-plan.json").read_text())
        self.assertEqual(len(plan["samples"]), 3)
        step = next(s for s in plan["steps"] if s["workflow"] == "fetal-sex")
        self.assertEqual(step["inputs"]["autosomes"], "dnp_Mother")
        record = self.runner.records[0][1]
        shared, = [m for m in record["parameters"]["sample_mapping"] if m.get("shared_fetal_sex_table")]
        self.assertEqual(shared["sample_id"], "dnp_Mother")
        self.assertEqual(Path(shared["container_path"]).name, self.paths["autosomes"].name)
        mounts = [m for m in record["mounts"].mappings if Path(m["host_path"]) == self.paths["autosomes"].resolve()]
        self.assertEqual(len(mounts), 1)

    def test_swapped_regions_are_rejected_before_record_creation(self):
        with self.assertRaises(ValidationError):
            self.workflows.fetal_sex(autosomes=self.paths["x"], x=self.paths["autosomes"], y=self.paths["y"])
        self.assertFalse(self.layout.runs_dir.exists())
        self.assertFalse(self.runner.calls)
