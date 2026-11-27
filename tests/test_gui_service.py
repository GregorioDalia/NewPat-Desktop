"""Desktop adapters preserve caller selection, validated plans and recorded outcomes."""
from __future__ import annotations

from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
import errno
import json
import io
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from nipat.errors import RuntimeExecutionError, RuntimeInterruptedError, ValidationError
from nipat.execution.progress import ProgressSnapshot
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.transport import DockerTransport
from nipat.gui.admission import DesktopAdmission
from nipat.gui.jobs import GuiRunner, Job, JobManager
from nipat.gui.plan import prepare_analysis
from nipat.gui.service import GuiService
from nipat.paths import ProjectLayout
from nipat.preferences import Preferences, PreferencesStore


class GuiFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.enterContext(patch("nipat.gui.jobs.DesktopAdmission",
                          side_effect=lambda runtime, ident: DesktopAdmission(runtime, ident, home=self.root)))
        project = self.root / "project"
        project.mkdir()
        (project / "compose.yaml").write_text("services: {}\n")
        self.layout = ProjectLayout(project, self.root, self.root / "data", self.root / "runs", project / "compose.yaml")
        self.store = PreferencesStore(self.root / "settings" / "preferences.json")
        self.samples = [{"id": name, "path": str(self.file(name + " with spaces.bam", name)), "kind": "bam"}
                        for name in ("Plasma", "Mother", "Father", "Child")]
        self.reference = self.root / "ref.fa"
        self.reference.write_bytes(b">chr1\nACGT\n")
        self.file("ref.fa.fai", "chr1\t4\t6\t4\t5\n")
        self.dnp_panel = self.file("dnp.tsv", "chr1\t2\t3\tCG\tAT\n")
        self.snp_panel = self.file("snp.tsv", "chr\tpos\tref\talt\nchr1\t2\tC\tA\n")
        self.dnp_freq = self.file("dnp-pop.tsv", "chr\tpos1\tpos2\tRef_f.pop\tAlt_f.pop\nchr1\t2\t3\t0.6\t0.4\n")
        self.snp_freq = self.file("snp-pop.tsv", "chr\tpos\tRef_f.pop\tAlt_f.pop\nchr1\t2\t0.6\t0.4\n")
        self.tables = {marker: [{"id": name, "path": str(self.file(marker + "-" + name + ".tsv",
            ("chr\tpos1\tpos2\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\nchr1\t2\t3\tCG\tAT\t50\t50\t0\t100\n"
             if marker == "DNP" else "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\nchr1\t2\tC\tA\t50\t50\t0\t100\n"))), "kind": marker.lower() + "-table"}
            for name in ("Plasma", "Mother", "Father", "Child")] for marker in ("DNP", "SNP")}

    def file(self, name, text):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def draft(self, caller="dnp", dnp=None, snp=None):
        dnp, snp = list(dnp or []), list(snp or [])
        branches = {"DNP": dnp, "SNP": snp}
        selected = set(dnp + snp)
        return {"name": "Esperimento à due campioni", "caller": caller,
                "samples": deepcopy(self.samples) if caller != "tables" else
                    (deepcopy(self.tables["DNP"]) if dnp else []) + (deepcopy(self.tables["SNP"]) if snp else []),
                "branches": branches, "reference": str(self.reference) if caller != "tables" else None,
                "resources": {"DNP": {"panel": str(self.dnp_panel), "popfreq": str(self.dnp_freq),
                                       "contamination_panel": str(self.dnp_panel)},
                              "SNP": {"panel": str(self.snp_panel), "popfreq": str(self.snp_freq),
                                       "contamination_panel": str(self.snp_panel)}},
                "families": {"cpi": [{"id": "Prenatal", "mother": "Plasma", "father": "Father"}] if "cpi" in selected else [],
                             "cpin": [{"id": "Postnatal", "mother": "Mother", "father": "Father", "child": "Child"}] if "cpin" in selected else []},
                "scientific_settings": {}, "execution": {}}

    def service(self, **kwargs):
        return GuiService(self.layout, preferences_store=self.store, **kwargs)


class GuiPlanTests(GuiFixture):
    def test_cli_experiment_offers_igv_for_recorded_bams_only(self):
        from nipat.execution.workflows import Workflows

        bam = Path(self.samples[0]["path"])
        runner = DockerComposeRunner(self.layout, dry_run=True, transport=DockerTransport(dry_run=True))
        run = Workflows(self.layout, runner).analyze(
            caller="snp", analyses=[], samples=[("Plasma", bam)], reference=self.reference,
            snp_panel=self.snp_panel, dnp_tables=[("Other", Path(self.tables["DNP"][0]["path"]))],
            dnp_analyses=["contamination"], dnp_contamination_panel=self.dnp_panel, run_name="cli-igv")
        service = self.service()
        self.assertTrue(service.call("runs.get", {"run_id": run.name})["has_igv_inputs"])
        self.assertEqual(service.call("run.igv", {"run_id": run.name}), {
            "reference": {"fasta": str(self.reference), "index": "",
                          "fasta_sha256": hashlib.sha256(self.reference.read_bytes()).hexdigest(),
                          "index_sha256": hashlib.sha256(Path(str(self.reference) + ".fai").read_bytes()).hexdigest()},
            "tracks": [{"name": "Plasma", "path": str(bam)}], "locus": "all"})

    def test_independent_callers_and_asymmetric_downstream_branches(self):
        for caller, expected in (("dnp", ["dnp-call"]), ("snp", ["snp-call"] * 4),
                                 ("both", ["dnp-call"] + ["snp-call"] * 4)):
            with self.subTest(caller=caller):
                prepared = prepare_analysis(self.draft(caller), self.layout)
                self.assertEqual([s["workflow"] for s in prepared.preview["steps"]], expected)
        prepared = prepare_analysis(self.draft("both", ["contamination"], ["cpi", "cpin"]), self.layout)
        ids = {s["id"] for s in prepared.preview["steps"]}
        self.assertIn("dnp_contamination", ids)
        self.assertIn("snp_cpi", ids)
        self.assertIn("snp_cpin", ids)
        self.assertNotIn("snp_contamination", ids)
        self.assertNotIn("dnp_cpi", ids)
        self.assertFalse(self.layout.runs_dir.exists(), "preview must not create a run")

    def test_named_reference_is_bound_to_the_reviewed_fasta_and_reopened_in_igv(self):
        from nipat.gui.results import ResultsStore
        from test_gui_igv import _bam

        entry = {"id": "reference-1", "build": "grch38", "label": "UCSC hg38",
                 "fasta": str(self.reference), "index": str(self.reference) + ".fai",
                 "naming": "chr", "fasta_sha256": hashlib.sha256(self.reference.read_bytes()).hexdigest(),
                 "index_sha256": hashlib.sha256(Path(str(self.reference) + ".fai").read_bytes()).hexdigest()}
        catalog = Mock()
        catalog.resolve.return_value = entry
        draft = self.draft("both")
        draft.update(reference_id=entry["id"], reference_genome={"build": "grch37"})
        for sample in draft["samples"]:
            sample["path"] = str(_bam(self.root, chromosome="chr1", length=4, name=sample["id"]))
        service = self.service()
        with patch.object(service, "reference_catalog", return_value=catalog):
            preview = service.plan_preview(draft)
        prepared = service._plans[preview["preview_id"]]
        catalog.resolve.assert_called_once_with(entry["id"])
        self.assertEqual(preview["reference_genome"], entry)
        self.assertEqual(prepared.draft["reference_genome"], entry)
        self.assertEqual(prepared.inputs["reference"], self.reference)
        results = ResultsStore(self.layout.runs_dir)
        with patch.object(results, "_context", return_value={"gui": {"draft": prepared.draft}}):
            reference, tracks = results.igv_sources("archived")
        self.assertEqual(reference, {"build": "grch38", "fasta": str(self.reference), "index": entry["index"],
                                     "index_sha256": entry["index_sha256"], "fasta_sha256": entry["fasta_sha256"]})
        self.assertEqual([t["name"] for t in tracks], [s["id"] for s in draft["samples"]])

        bad = deepcopy(draft)
        bad["samples"][0]["path"] = str(_bam(self.root, chromosome="chr1", length=5, name="wrong-build"))
        with self.assertRaisesRegex(ValidationError, "BAM and FASTA lengths differ"):
            prepare_analysis(bad, self.layout, language="en", reference_catalog=catalog)
        bad["samples"][0]["path"] = str(_bam(self.root, chromosome="1", length=4, name="other-naming"))
        with self.assertRaisesRegex(ValidationError, "BAM usa 1.*FASTA usa chr1"):
            prepare_analysis(bad, self.layout, language="it", reference_catalog=catalog)
        bad = deepcopy(draft)
        bad["resources"]["SNP"]["panel"] = str(self.file("wrong-panel.tsv", "chr\tpos\tref\talt\nchr2\t9\tC\tT\n"))
        with self.assertRaisesRegex(ValidationError, "Panel window chr2:8-10 is outside FASTA"):
            prepare_analysis(bad, self.layout, language="en", reference_catalog=catalog)

        draft["reference"] = str(self.file("different.fa", ">ref\nA\n"))
        with self.assertRaisesRegex(ValidationError, "differs"):
            prepare_analysis(draft, self.layout, language="en", reference_catalog=catalog)
        del draft["reference_id"]
        draft["reference"] = str(self.reference)
        manual = prepare_analysis(draft, self.layout)
        self.assertEqual(manual.preview["reference_genome"]["build"], "custom")
        self.assertNotIn("id", manual.draft["reference_genome"])
        self.assertEqual(manual.draft["reference_genome"]["fasta_sha256"], entry["fasta_sha256"])

    def test_tables_only_never_schedule_calling_or_require_a_reference(self):
        prepared = prepare_analysis(self.draft("tables", snp=["contamination"]), self.layout)
        self.assertEqual([s["workflow"] for s in prepared.preview["steps"]], ["contamination"])
        self.assertEqual(prepared.preview["analyses_by_marker"], {"SNP": ["contamination"]})
        self.assertEqual(prepared.inputs["samples"], [])
        self.assertIsNone(prepared.inputs["reference"])

    def test_tables_without_selected_analysis_are_rejected(self):
        with self.assertRaises(ValidationError):
            prepare_analysis(self.draft("tables"), self.layout)

    def test_pileup_only_snp_preserves_input_mode(self):
        draft = self.draft("snp")
        pileup = self.file("reads.pileup", "chr1\t1\tA\t2\t.,\tII\tr1,r2\nchr1\t2\tC\t2\t.,\tII\tr1,r2\nchr1\t3\tG\t2\t.,\tII\tr1,r2\n")
        draft.update(samples=[{"id": "Sample", "kind": "snp-pileup", "path": str(pileup)}], reference=None)
        prepared = prepare_analysis(draft, self.layout)
        self.assertEqual(prepared.preview["steps"][0]["parameters"]["mode"], "pileup")
        self.assertIsNone(prepared.preview["steps"][0]["inputs"]["reference"])

    def test_duplicate_roles_and_out_of_range_parameters_fail_before_any_run(self):
        draft = self.draft("both", ["cpin"], ["cpi"])
        draft["families"]["cpin"][0]["child"] = "Mother"
        with self.assertRaises(ValidationError):
            prepare_analysis(draft, self.layout)
        draft = self.draft()
        draft["scientific_settings"] = {"dnp-call": {"other_fraction_max": 1.5}}
        with self.assertRaises(ValidationError):
            prepare_analysis(draft, self.layout)
        self.assertFalse(self.layout.runs_dir.exists())

    def test_relative_inputs_unknown_fields_and_nonfinite_execution_are_rejected(self):
        draft = self.draft()
        draft["samples"][0]["path"] = "relative.bam"
        with self.assertRaisesRegex(ValidationError, "assoluto"):
            prepare_analysis(draft, self.layout)
        draft = self.draft()
        draft["command"] = "anything"
        with self.assertRaises(ValidationError):
            prepare_analysis(draft, self.layout)
        draft = self.draft()
        draft["execution"] = {"cpus": float("nan")}
        with self.assertRaises(ValidationError):
            prepare_analysis(draft, self.layout)

    def test_preview_freezes_settings_and_detects_input_changes(self):
        draft = self.draft()
        preferences = Preferences(scientific_settings={"dnp-call": {"max_depth": 2222}}, execution={"max_workers": 2})
        prepared = prepare_analysis(draft, self.layout, preferences)
        draft["samples"].clear()
        preferences.scientific_settings["dnp-call"]["max_depth"] = 5000
        self.assertEqual(prepared.preview["effective_settings"]["dnp-call"]["max_depth"], 2222)
        self.assertEqual(len(prepared.inputs["samples"]), 4)
        self.assertEqual(prepared.execution.max_workers, 2)
        Path(self.samples[0]["path"]).write_bytes(b"changed input")
        with self.assertRaisesRegex(ValidationError, "cambiato"):
            prepared.assert_inputs_unchanged()


class GuiServiceTests(GuiFixture):
    def test_verified_macos_update_can_be_revealed_without_starting_an_installer(self):
        from nipat.updates import UpdateAsset, UpdateCheck, UpdateOffer
        for platform in ("darwin-arm64", "darwin-x86_64"):
            with self.subTest(platform=platform):
                package = self.file(platform + ".pkg", "test package")
                asset = UpdateAsset(platform, package.name, package.stat().st_size,
                                    hashlib.sha256(package.read_bytes()).hexdigest(), "https://example.test/pkg")
                offer = UpdateOffer("0.9.11", "v0.9.11", "stable", "a" * 40, 1, asset, "https://example.test/release")
                service = self.service()
                with (patch("nipat.updates.UpdateClient") as client,
                      patch("nipat.updates.detect_platform", return_value=platform),
                      patch("nipat.update_handoff.update_cache_directory", return_value=self.root),
                      patch("nipat.update_handoff.begin_update") as handoff,
                      patch("nipat.gui.service.subprocess.run") as native):
                    client.return_value.check.return_value = UpdateCheck("available", "Available", offer)
                    client.return_value.download.return_value = package
                    token = service.call("updates.check", {"channel": "stable"})["offer_id"]
                    with self.assertRaises(ValidationError):
                        service.call("updates.reveal", {"offer_id": token})
                    downloaded = service.call("updates.download", {"offer_id": token})
                    self.assertEqual(downloaded["path"], str(package))
                    native.assert_not_called()
                    self.assertEqual(service.call("updates.reveal", {"offer_id": token}), {"status": "revealed"})
                    native.assert_called_once_with(["/usr/bin/open", "-R", str(package)], check=True, timeout=15)
                    self.assertEqual(service.call("updates.install", {"offer_id": token, "confirmed": True}),
                                     {"status": "manual_install", "path": str(package), "close_required": False})
                    handoff.assert_not_called()

    def test_result_statistics_cache_survives_navigation_but_not_locale_change(self):
        service = self.service()
        first = service._results()
        self.assertIs(first, service._results())
        service.ui_save({"language": "en", "reduce_motion": False})
        translated = service._results()
        self.assertIsNot(first, translated)
        self.assertEqual(translated.language, "en")
        self.assertIs(translated, service._results())

    def test_bootstrap_contains_full_catalog_without_running_engine(self):
        with patch.object(DockerComposeRunner, "doctor", side_effect=AssertionError("unexpected runtime")):
            value = self.service().call("bootstrap")
        self.assertEqual(set(value["settings"]["workflows"]), {"dnp-call", "snp-call", "contamination", "cpi", "cpin", "fetal-sex"})
        post = value["settings"]["workflows"]["cpin"]["parameters"]
        self.assertTrue(all(post["include_" + pair]["default"] for pair in ("hom_hom", "hom_het", "het_hom", "het_het")))
        self.assertNotIn("min_child_reads", post)
        self.assertIsNone(post["min_coverage"]["default"])
        self.assertIsNone(value["settings"]["workflows"]["cpi"]["parameters"]["min_fetal_percent"]["default"])
        self.assertEqual(value["jobs"], [])
        self.assertEqual(value["ui"], {"language": "it", "reduce_motion": False})

    def test_preferences_merge_preserves_concurrent_unrelated_edit(self):
        service = self.service()
        original = service.call("preferences.get")
        requested = deepcopy(original)
        requested["execution"] = {"max_workers": 3}
        self.store.save(Preferences(update_channel="testing"))
        saved = service.call("preferences.save", {"preferences": requested, "baseline": original})
        self.assertEqual(saved["update_channel"], "testing")
        self.assertEqual(saved["execution"]["max_workers"], 3)

    def test_ui_language_and_motion_are_separate_from_scientific_defaults(self):
        service = self.service()
        original = service.call("preferences.get")
        service.call("ui.save", {"preferences": {"language": "en", "reduce_motion": True}})
        self.assertEqual(service.call("ui.get"), {"language": "en", "reduce_motion": True})
        self.assertEqual(service.call("preferences.get"), original)

    def test_unknown_method_is_not_evaluated_and_dialog_is_injected(self):
        callback = Mock(return_value={"paths": []})
        service = self.service(host={"dialog.open": callback})
        self.assertEqual(service.call("dialog.open", {"kind": "files", "multiple": True}), {"paths": []})
        callback.assert_called_once_with({"kind": "files", "multiple": True})
        with self.assertRaises(KeyError):
            service.call("__class__")

    def test_preview_token_is_one_use_and_changed_inputs_never_start(self):
        jobs = Mock()
        jobs.start.return_value = {"id": "job"}
        service = self.service(jobs=jobs)
        preview = service.call("plan.preview", {"draft": self.draft()})
        result = service.call("analysis.start", {"preview_id": preview["preview_id"]})
        self.assertEqual(result, {"id": "job"})
        with self.assertRaises(ValidationError):
            service.call("analysis.start", {"preview_id": preview["preview_id"]})
        manager = JobManager()
        prepared = prepare_analysis(self.draft(), self.layout)
        Path(self.samples[0]["path"]).write_text("new content")
        with self.assertRaisesRegex(ValidationError, "Plasma with spaces.bam"):
            manager.start(prepared)
        self.assertEqual(manager.list(), [])

    def test_changed_and_missing_files_identified_in_the_selected_language(self):
        service = self.service()
        for language, changed, missing in (("en", "has changed", "Input unavailable"),
                                            ("it", "è cambiato", "Input non disponibile")):
            with self.subTest(language=language):
                service.call("ui.save", {"preferences": {"language": language, "reduce_motion": False}})
                path = Path(self.samples[0]["path"])
                path.write_text("original")
                for change, expected in ((lambda: path.write_text("changed contents"), changed),
                                         (path.unlink, missing)):
                    preview = service.call("plan.preview", {"draft": self.draft()})
                    change()
                    with self.assertRaises(ValidationError) as error:
                        service.call("analysis.start", {"preview_id": preview["preview_id"]})
                    self.assertIn(expected, str(error.exception))
                    self.assertIn(path.name, str(error.exception))

    def test_preview_token_cannot_launch_twice_while_first_start_is_pending(self):
        entered, release = threading.Event(), threading.Event()
        jobs = Mock()

        def start(prepared):
            entered.set()
            self.assertTrue(release.wait(3))
            return {"id": "first"}

        jobs.start.side_effect = start
        service = self.service(jobs=jobs)
        preview = service.call("plan.preview", {"draft": self.draft()})
        params = {"preview_id": preview["preview_id"]}
        results = []
        worker = threading.Thread(target=lambda: results.append(service.call("analysis.start", params)))
        worker.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaises(ValidationError):
                service.call("analysis.start", params)
        finally:
            release.set()
            worker.join(3)
        self.assertEqual(results, [{"id": "first"}])
        jobs.start.assert_called_once()

    def test_resource_apply_uses_server_held_preview_and_preserves_confirmation(self):
        change = Mock()
        change.as_dict.return_value = {"before": {}, "after": {"cpus": 2, "memory_mib": 1024}}
        manager = Mock()
        manager.preview.return_value = change
        manager.apply.return_value = {"status": "saved-restart-required"}
        service = self.service(resource_factory=lambda _: manager)
        preview = service.call("resources.preview", {"cpus": 2, "memory_mib": 1024})
        service.call("resources.apply", {"preview_id": preview["preview_id"], "confirmed": True})
        manager.apply.assert_called_once_with(change, confirmed=True, restart_confirmed=False)
        with self.assertRaises(ValidationError):
            service.call("resources.apply", {"preview_id": preview["preview_id"], "confirmed": True})


class GuiRuntimeFixture(GuiFixture):
    def setUp(self):
        super().setUp()
        # These adapter tests simulate runtime operations; selecting the host's
        # installed WSL/Lima environment is covered by the transport tests.
        transport = patch.object(DockerTransport, "from_environment",
                                 side_effect=lambda **kwargs: DockerTransport(**kwargs))
        transport.start()
        self.addCleanup(transport.stop)


class GuiJobTests(GuiRuntimeFixture):
    def test_input_replaced_during_startup_requires_a_new_review(self):
        source = Path(self.samples[0]["path"])
        replacement = source.with_suffix(".replacement")
        replacement.write_bytes(b"X" * source.stat().st_size)
        shutil.copystat(source, replacement)
        original = source.stat()

        def runner_factory(prepared, job):
            # Initial submission checks succeeded, but the user's file changes
            # before the runner records its own evidence and builds the command.
            replacement.replace(source)
            changed = source.stat()
            self.assertEqual((changed.st_size, changed.st_mtime_ns),
                             (original.st_size, original.st_mtime_ns))
            runner = GuiRunner(prepared, job)
            runner.dry_run = True
            return runner

        manager = JobManager(runner_factory=runner_factory)
        service = self.service(jobs=manager)
        preview = service.call("plan.preview", {"draft": self.draft()})
        submitted = service.call("analysis.start", {"preview_id": preview["preview_id"]})
        finished = manager.wait(submitted["id"], 5)
        self.assertEqual(finished["status"], "failed", finished)
        self.assertIn(source.name, finished["error"])
        record = json.loads((self.layout.runs_dir / finished["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["commands"], [])

    def test_preparation_reports_unknown_runtime_progress_and_measured_input_bytes(self):
        prepared = prepare_analysis(self.draft(), self.layout)
        job = Job(prepared)
        runner = GuiRunner(prepared, job)
        with patch.object(DockerComposeRunner, "_prepare_runtime", return_value="ready"):
            self.assertEqual(runner._prepare_runtime(), "ready")
        progress = job.snapshot()["progress"]
        self.assertEqual(progress["phase"], "preparing-runtime")
        self.assertIsNone(progress["completed"])
        self.assertIsNone(progress["total"])
        with patch.object(DockerComposeRunner, "_describe_bundled_engine", return_value="verified"):
            self.assertEqual(runner._describe_bundled_engine(), "verified")
        self.assertEqual(job.snapshot()["progress"]["phase"], "verifying-engine")
        runner._hash_progress(self.reference, 4, 16)
        progress = job.snapshot()["progress"]
        self.assertEqual((progress["phase"], progress["completed"], progress["total"], progress["unit"]),
                         ("checking-inputs", 4, 16, "bytes"))
        self.assertGreaterEqual(progress["elapsed_seconds"], 0)
        self.assertFalse(job.done.is_set())

    def test_activity_results_stay_bound_to_the_jobs_directory_after_archive_change(self):
        manager = JobManager()
        service = self.service(jobs=manager)
        job = Job(prepare_analysis(self.draft(), self.layout))
        manager._jobs[job.id] = job
        with self.assertRaises(ValidationError):
            service.call("jobs.result_id", {"job_id": job.id})

        def seed(path, name):
            path.mkdir(parents=True)
            (path / "run.json").write_text(json.dumps({"schema_version": 1, "status": "succeeded",
                                                       "workflow": "dnp-call"}), encoding="utf-8")
            (path / "gui.json").write_text(json.dumps({"schema_version": 1, "name": name}), encoding="utf-8")
        def switch_archive(destination):
            before = service.call("preferences.get")
            service.call("preferences.save", {"baseline": before, "preferences": {**before, "runs_dir": destination}})
        def open_card():
            result = service.call("jobs.result_id", {"job_id": job.id})
            return service.call("runs.get", result)

        job.run_dir = self.layout.runs_dir / "analysis-one"
        seed(job.run_dir, "Original")
        self.assertEqual(open_card()["id"], "analysis-one")
        job.status = "succeeded"
        job.finished_at = "2026-11-23T12:00:00Z"
        job.done.set()
        original_root = service.call("preferences.get")["runs_dir"]
        alternate = self.root / "alternate"
        copied = alternate / job.run_dir.name
        seed(copied, "Copy")
        switch_archive(str(alternate))
        selected = open_card()
        self.assertEqual(selected["name"], "Original")
        self.assertTrue(selected["id"].startswith("imported-"))
        self.assertEqual(open_card()["id"], selected["id"])
        self.assertEqual({r["name"] for r in service.call("runs.list")["runs"]}, {"Original", "Copy"})
        switch_archive(original_root)
        self.assertEqual([r["name"] for r in service.call("runs.list")["runs"]], ["Original"])
        switch_archive(str(alternate))
        removed = service.call("jobs.remove", {"job_id": job.id})
        self.assertEqual(removed["archive_id"], selected["id"])
        self.assertEqual([r["name"] for r in service.call("runs.list")["runs"]], ["Copy"])
        self.assertTrue(all((p / "run.json").is_file() for p in (job.run_dir, copied)))

    def test_activity_summary_and_on_demand_log_cursor(self):
        manager = JobManager()
        job = Job(prepare_analysis(self.draft(), self.layout))
        manager._jobs[job.id] = job
        service = self.service(jobs=manager)
        job.log("initial\nsecond")
        for phase in ("a", "b", "c", "d", "e", "f", "f"):
            job.progressed(ProgressSnapshot(status="running", elapsed_seconds=1,
                           phase=phase, sample_ids=("Plasma",), completed=2, total=10))
        summary, = service.call("jobs.list", {"include_logs": False})
        self.assertNotIn("logs", summary)
        self.assertEqual(summary["sample_count"], 4)
        self.assertEqual(summary["event_revision"], 6)
        self.assertEqual([e["progress"]["phase"] for e in summary["events"]], list("bcdef"))
        self.assertEqual(service.call("jobs.get", {"job_id": job.id})["logs"], ["initial", "second"])
        params = {"job_id": job.id, "after": 1}
        self.assertEqual(service.call("jobs.logs", params), {
            "lines": ["second"], "revision": 2, "limit": 250, "reset": False})
        self.assertEqual(manager.logs(job.id, 2)["lines"], [])
        for number in range(260):
            job.log(str(number))
        shifted = service.call("jobs.logs", params)
        self.assertTrue(shifted["reset"])
        self.assertEqual(shifted["lines"], [str(i) for i in range(10, 260)])
        self.assertEqual(shifted["revision"], 262)
        for bad in (-1, True, "1"):
            with self.assertRaises(ValidationError):
                manager.logs(job.id, bad)

    def test_active_status_covers_final_report_persistence(self):
        reporting = threading.Event()
        release = threading.Event()
        class FinalizingRunner(GuiRunner):
            def __init__(self, prepared, job):
                super().__init__(prepared, job)
                def outcome(value):
                    job.outcome(value)
                    reporting.set()
                    release.wait(5)
                self._run_finished_callback = outcome
            def _prepare_runtime(self):
                raise RuntimeExecutionError("runtime unavailable")
        manager = JobManager(runner_factory=FinalizingRunner)
        prepared = prepare_analysis(self.draft(), self.layout)
        try:
            job = manager.start(prepared)
            self.assertTrue(reporting.wait(5))
            self.assertTrue(manager.active()["active"])
            second = manager.start(prepared)
            self.assertNotEqual(job["id"], second["id"])
            with self.assertRaises(ValidationError):
                self.service(jobs=manager).call("jobs.remove", {"job_id": job["id"]})
        finally:
            release.set()
        self.assertEqual(manager.wait(job["id"], 5)["status"], "failed")
        self.assertEqual(manager.wait(second["id"], 5)["status"], "failed")
        self.assertFalse(manager.active()["active"])

    def test_simultaneous_runs_cancel_and_remove_only_selected_experiment(self):
        release = threading.Event()
        both_running = threading.Barrier(3)
        class PausedRunner(GuiRunner):
            # Exercise the real client and archive with a controlled engine boundary.
            def _prepare_runtime(self): pass
            def _record_resource_snapshot(self): pass
            def _describe_bundled_engine(self): self._image_id = "sha256:" + "1" * 64

            def _run_command(self, command, *, working_dir=None):
                output = self.last_run_dir / "output" / "workflow"
                output.mkdir()
                (output / "calls.tsv").write_text(f"sample\tchr\tpos1\tpos2\n{self.job.id}\tchr1\t2\t3\n",
                                                  encoding="utf-8")
                both_running.wait(timeout=5)
                while not release.wait(.02):
                    self._cancel_point()
                self._cancel_point()
                plan = json.loads((self.last_run_dir / "work/engine-plan.json").read_text(encoding="utf-8"))
                state = {"schema_version": 1, "interface": "workflow-plan-execution-v2", "status": "succeeded",
                         "steps": [{"id": step["id"], "workflow": step["workflow"], "status": "succeeded"}
                                   for step in plan["steps"]]}
                (output / "workflow-state.json").write_text(json.dumps(state), encoding="utf-8")
        manager = JobManager(runner_factory=PausedRunner, reconcile=lambda *_a, **_k: {"containers": []})
        service = self.service(jobs=manager)
        def launch():
            preview = service.call("plan.preview", {"draft": self.draft()})
            return service.call("analysis.start", {"preview_id": preview["preview_id"]})["id"]
        first, second = launch(), launch()
        try:
            both_running.wait(timeout=5)
            self.assertEqual({row["id"] for row in manager.active()["jobs"]}, {first, second})
            service.call("jobs.cancel", {"job_id": first})
            cancelled = manager.wait(first, 5)
            self.assertEqual(cancelled["status"], "interrupted")
            original = self.layout.runs_dir / cancelled["run_id"] / "run.json"
            evidence = original.read_bytes()
            partial_output = original.parent / "output/workflow/calls.tsv"
            partial_bytes = partial_output.read_bytes()
            self.assertIn(first.encode(), partial_bytes)
            with self.assertRaises(ValidationError):
                service.call("jobs.remove", {"job_id": second})
            self.assertTrue(service.call("jobs.remove", {"job_id": first})["outputs_preserved"])
            self.assertEqual([row["id"] for row in manager.list()], [second])
            active = manager.active()["jobs"]
            self.assertEqual([row["id"] for row in active], [second])
            self.assertFalse(active[0]["cancel_requested"])
            self.assertNotEqual(active[0]["run_id"], cancelled["run_id"])
            self.assertEqual([row["id"] for row in service.call("runs.list")["runs"]], [active[0]["run_id"]])
            self.assertEqual(original.read_bytes(), evidence)
        finally:
            release.set()
        other = manager.wait(second, 5)
        self.assertEqual(other["status"], "succeeded", other)
        self.assertFalse(manager.active()["active"])
        # A fresh GUI session reads the persisted hide decision and the surviving result.
        reopened = self.service()
        survivor, = reopened.call("runs.list")["runs"]
        self.assertEqual((survivor["id"], survivor["status"]), (other["run_id"], "succeeded"))
        self.assertEqual(partial_output.read_bytes(), partial_bytes)
        self.assertEqual(original.read_bytes(), evidence)
        completed_output = self.layout.runs_dir / other["run_id"] / "output/workflow/calls.tsv"
        self.assertIn(second.encode(), completed_output.read_bytes())
        self.assertTrue(service.call("runs.remove", {"run_id": other["run_id"]})["outputs_preserved"])
        self.assertEqual(manager.list(), [])
        self.assertEqual(service.call("runs.list")["total"], 0)

    def test_jobs_preparing_together_share_only_the_remaining_guest_quota(self):
        from nipat.execution.options import ExecutionOptions
        prepared = prepare_analysis(self.draft(), self.layout)
        def runner(options):
            job = Job(replace(prepared, execution=options))
            instance = GuiRunner(job.prepared, job)
            instance._record = Mock(data={})
            return instance
        first, second, third = (runner(options) for options in (
            ExecutionOptions(), ExecutionOptions(cpus=0.75, memory_mb=900), ExecutionOptions()))
        def snapshot(**_):
            return {"runtime": {"effective": {"cpus": 4, "memory_mib": 3905}}}
        with ExitStack() as context:
            context.enter_context(patch("nipat.resources.ResourceManager.snapshot", side_effect=snapshot))
            for instance in (first, second):
                context.enter_context(instance._admission.registration())
                # Both jobs are registered while inputs are being prepared.
            first._record_resource_snapshot()
            second._record_resource_snapshot()
            context.enter_context(third._admission.registration())
            third._record_resource_snapshot()
            self.assertEqual((first.options.cpus, first.options.memory_mb), (2, 1952))
            self.assertEqual((second.options.cpus, second.options.memory_mb), (0.75, 900))
            self.assertEqual((third.options.cpus, third.options.memory_mb), (1.25, 1053))
            for instance in (first, second, third):
                budget = instance._record.data["resource_budget"]
                self.assertEqual(budget["cpu_limit"], instance.options.cpus)
                self.assertEqual(budget["memory_capacity_mib"], instance.options.memory_mb)
                self.assertEqual(instance.options.compose_limits()["mem_limit"], instance.options.memory_mb * 2**20)

    def test_desktop_step_grant_requires_matching_ack_and_never_resizes_compose(self):
        from nipat.execution.options import ExecutionOptions
        prepared = prepare_analysis(self.draft(), self.layout)
        runner = GuiRunner(prepared, Job(prepared))
        run_dir = self.layout.new_run_dir("analysis", "step-grants")
        runner._record = Mock(data={}, run_dir=run_dir)
        runner._bundled_workflow = "workflow-plan-all"
        snapshot = {"runtime": {"effective": {"cpus": 4, "memory_mib": 3905}}}
        contender = DesktopAdmission(runner._transport.metadata, "late", home=self.root)
        with runner._admission.registration(), patch("nipat.resources.ResourceManager.snapshot", return_value=snapshot):
            runner._record_resource_snapshot()
            with patch.object(DockerComposeRunner, "_describe_bundled_engine", return_value={}):
                runner._describe_bundled_engine()
            self.assertIsNone(runner._step_scheduler)
            with patch.object(DockerComposeRunner, "_describe_bundled_engine",
                              return_value={"desktop_scheduling": "step-budget-v1"}):
                runner._describe_bundled_engine()
            scheduler = runner._step_scheduler
            runner._write_engine_compose("sha256:" + "0" * 64)
            compose_path = run_dir / "work/engine-compose.json"
            before = compose_path.read_bytes()
            service = json.loads(before)["services"]["scientific"]
            self.assertEqual(service["environment"]["NIPAT_DESKTOP_SCHEDULER"],
                             str(self.layout.container_path(scheduler.directory)))
            self.assertNotIn("mem_limit", service)
            # The registry timestamp may be identical across two ticket changes.
            # Advance the observer clock to the periodic rescan on each change.
            clock = self.enterContext(patch("nipat.gui.admission.time", wraps=time))
            clock.monotonic.return_value = 0.0
            scheduler.poll()
            self.assertFalse((scheduler.directory / "request.json").exists())
            with contender.registration():
                self.assertIsNone(contender.try_admit(4, 3905, ExecutionOptions(), Mock()))
                clock.monotonic.return_value = 2.0
                scheduler.poll()
                request = json.loads((scheduler.directory / "request.json").read_text())
                runner._admission._write(scheduler.directory / "ack.json", {**request, "token": "f" * 32})
                scheduler.poll()
                self.assertFalse((scheduler.directory / "grant.json").exists())
                self.assertIsNone(contender.try_admit(4, 3905, ExecutionOptions(), Mock()))
                runner._admission._write(scheduler.directory / "ack.json", request)
                replace_file = Path.replace
                attempts = []
                def transient_sharing_violation(path, target):
                    if target.name == "grant.json":
                        attempts.append(target)
                        if len(attempts) == 1:
                            raise PermissionError(errno.EACCES, "Sharing violation")
                    return replace_file(path, target)
                with patch.object(Path, "replace", transient_sharing_violation):
                    scheduler.poll()
                self.assertEqual(len(attempts), 2)
                grant = json.loads((scheduler.directory / "grant.json").read_text())
                self.assertEqual(grant["token"], request["token"])
                self.assertEqual((grant["budget"]["cpu_limit"], grant["budget"]["memory_capacity_mib"]),
                                 (2, 1952))
                admitted = contender.try_admit(4, 3905, ExecutionOptions(), Mock())
                self.assertEqual((admitted.cpus, admitted.memory_mib), (2, 1953))
            clock.monotonic.return_value = 4.0
            scheduler.poll()
            resume = json.loads((scheduler.directory / "request.json").read_text())
            self.assertNotEqual(request["token"], resume["token"])
            scheduler.poll()  # Delayed acknowledgement for the initial request.
            self.assertEqual(json.loads((scheduler.directory / "grant.json").read_text()), grant)
            runner._admission._write(scheduler.directory / "ack.json", resume)
            scheduler.poll()
            journal = [json.loads(row) for row in (scheduler.directory / "grants.jsonl").read_text().splitlines()]
            self.assertEqual([row["budget"]["memory_capacity_mib"] for row in journal], [1952, 3905])
            self.assertEqual(compose_path.read_bytes(), before)

    def test_default_run_keeps_full_capacity_and_later_run_waits_or_cancels(self):
        prepared = prepare_analysis(self.draft(), self.layout)
        def make():
            instance = GuiRunner(prepared, Job(prepared))
            instance._record = Mock(data={})
            return instance
        def snapshot(**_):
            return {"runtime": {"effective": {"cpus": 4, "memory_mib": 3905}}}
        first, second, third = make(), make(), make()
        with ExitStack() as context:
            context.enter_context(patch("nipat.resources.ResourceManager.snapshot", side_effect=snapshot))
            with first._admission.registration():
                first._record_resource_snapshot()
                self.assertIsNone(first.options.memory_mb)
                self.assertIsNone(first.options.cpus)
                self.assertEqual(first._record.data["resource_budget"]["memory_budget_mib"], 3124)
                context.enter_context(second._admission.registration())
                with third._admission.registration():
                    waiting = threading.Event()
                    original = third._preparation_progress
                    def notify(phase):
                        original(phase)
                        waiting.set()
                    third._preparation_progress = notify
                    outcome = []
                    def wait_for_capacity():
                        try:
                            third._record_resource_snapshot()
                        except KeyboardInterrupt:
                            outcome.append("cancelled")
                    worker = threading.Thread(target=wait_for_capacity)
                    worker.start()
                    try:
                        self.assertTrue(waiting.wait(3))
                        self.assertEqual(third.job.snapshot()["progress"]["phase"], "waiting-for-resources")
                    finally:
                        third.job.cancel_event.set()
                        worker.join(3)
                    self.assertEqual(outcome, ["cancelled"])
            # The second job was registered before the first completed. Its
            # budget must depend on current admissions at computation start.
            second._record_resource_snapshot()
            self.assertEqual(second._record.data["resource_budget"]["memory_budget_mib"], 3124)
            self.assertIsNone(second.options.memory_mb)

    def test_crashed_session_releases_only_after_runtime_confirms_its_project_is_idle(self):
        from nipat.execution.options import ExecutionOptions
        runtime = {"backend": "native"}
        # Leave a real cross-process registration behind, without running its
        # Python cleanup. The OS must release both Windows and POSIX owner locks.
        source = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from nipat.execution.options import ExecutionOptions
from nipat.gui.admission import DesktopAdmission
ticket = DesktopAdmission({"backend": "native"}, "orphan", home=Path(sys.argv[2]))
with ticket.registration():
    assert ticket.try_admit(4, 3905, ExecutionOptions(), lambda job: True) is not None
    print("running", flush=True)
    sys.stdin.readline()
    os._exit(0)
"""
        waiting = DesktopAdmission(runtime, "waiting", home=self.root)
        idle = Mock(side_effect=[False, True, True])
        with subprocess.Popen([sys.executable, "-c", source, str(Path(__file__).resolve().parents[1] / "src"),
                               str(self.root)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
            try:
                self.assertEqual(child.stdout.readline().strip(), "running")
                with waiting.registration(), patch("nipat.gui.admission.time", wraps=time) as clock:
                    clock.monotonic.side_effect = [1, 4, 7]
                    clock.monotonic_ns.side_effect = time.monotonic_ns
                    self.assertIsNone(waiting.try_admit(4, 3905, ExecutionOptions(), idle))
                    idle.assert_not_called()
                    child.communicate("\n", timeout=10)
                    self.assertEqual(child.returncode, 0)
                    for _ in range(3):
                        self.assertIsNone(waiting.try_admit(4, 3905, ExecutionOptions(), idle))
                    allocation = waiting.try_admit(4, 3905, ExecutionOptions(), idle)
                    self.assertEqual((allocation.cpus, allocation.memory_mib), (4, 3905))
            finally:
                if child.poll() is None:
                    child.kill()
        self.assertEqual([call.args for call in idle.call_args_list], [("orphan",)] * 3)

    def test_uncertain_partial_cleanup_does_not_permanently_reduce_future_runs(self):
        from nipat.execution.options import ExecutionOptions
        first, next_job = [DesktopAdmission({"backend": "native"}, name, home=self.root)
                           for name in ("first", "next")]
        with first.registration():
            first.try_admit(4, 4096, ExecutionOptions(cpus=1, memory_mb=1024), Mock())
            first.unconfirmed_cleanup = True
        idle = Mock(return_value=True)
        with next_job.registration(), patch("nipat.gui.admission.time", wraps=time) as clock:
            clock.monotonic.side_effect = [1, 4]
            clock.monotonic_ns.side_effect = time.monotonic_ns
            self.assertIsNone(next_job.try_admit(4, 4096, ExecutionOptions(), idle))
            self.assertIsNone(next_job.try_admit(4, 4096, ExecutionOptions(), idle))
            allocation = next_job.try_admit(4, 4096, ExecutionOptions(), idle)
            self.assertEqual((allocation.cpus, allocation.memory_mib), (4, 4096))

    def test_missing_capacity_serializes_calculations_and_errors_return_the_quota(self):
        from nipat.execution.options import ExecutionOptions
        first, second = [DesktopAdmission({"backend": "native"}, name, home=self.root)
                         for name in ("first", "second")]
        options = ExecutionOptions()
        for memory in (None, 127):
            with self.subTest(memory=memory), second.registration():
                with self.assertRaisesRegex(ValueError, "calculation"), first.registration():
                    allocated = first.try_admit(4, memory, options, Mock())
                    self.assertEqual((allocated.cpus, allocated.memory_mib, allocated.participants), (None, None, 1))
                    self.assertIsNone(second.try_admit(4, 4096, options, Mock()))
                    raise ValueError("calculation")
                self.assertEqual(second.try_admit(4, 4096, options, Mock()).memory_mib, 4096)

    def test_runtime_startup_wait_can_be_cancelled_independently(self):
        from concurrent.futures import ThreadPoolExecutor
        prepared = prepare_analysis(self.draft(), self.layout)
        first, second = [GuiRunner(prepared, Job(prepared)) for _ in range(2)]
        for runner in (first, second):
            runner._transport = Mock(backend="lima")
        self.assertNotEqual(first._base_command()[-1], second._base_command()[-1])
        entered, release = threading.Event(), threading.Event()
        def ensure(runner):
            self.assertIs(runner, first)
            entered.set()
            self.assertTrue(release.wait(5))
        with ThreadPoolExecutor(2) as threads, patch.object(DockerComposeRunner, "_ensure_backend", ensure):
            starting = threads.submit(first._ensure_backend)
            try:
                self.assertTrue(entered.wait(2))
                waiting = threads.submit(second._ensure_backend)
                second.job.cancel_event.set()
                with self.assertRaises(KeyboardInterrupt):
                    waiting.result(timeout=2)
            finally:
                release.set()
            starting.result(timeout=2)

    def test_native_capture_log_contract_handles_success_and_runtime_failure(self):
        prepared = prepare_analysis(self.draft(), self.layout)
        job = Job(prepared)
        runner = GuiRunner(prepared, job)
        runner._log = io.StringIO()
        for code in (0, 1):
            with self.subTest(code=code), patch("nipat.execution.runner.subprocess.run", return_value=
                    subprocess.CompletedProcess(["runtime"], code, "runtime output\n", "runtime detail\n")):
                if code:
                    with self.assertRaises(RuntimeExecutionError):
                        runner._capture_process(["runtime"])
                else:
                    self.assertEqual(runner._capture_process(["runtime"]), "runtime output")
        self.assertIn("runtime output", runner._log.getvalue())
        self.assertIn("runtime detail", job.snapshot()["logs"])

    def test_environment_capture_log_contract_handles_success_and_runtime_failure(self):
        def doctor(runner, check_runtime):
            runner._capture_process(["runtime"])
        for code in (0, 1):
            with self.subTest(code=code), patch.object(DockerComposeRunner, "doctor", doctor), \
                    patch("nipat.execution.runner.subprocess.run", return_value=
                          subprocess.CompletedProcess(["runtime"], code, "checked\n", "detail\n")):
                if code:
                    with self.assertRaises(RuntimeExecutionError):
                        self.service().environment_check()
                else:
                    result = self.service().environment_check()
                    self.assertEqual(result["status"], "passed")
                    self.assertIn("checked", result["logs"])

    def test_job_executes_existing_workflow_plan_and_archives_reviewed_config(self):
        def factory(prepared, job):
            runner = GuiRunner(prepared, job)
            runner.dry_run = True
            return runner
        manager = JobManager(runner_factory=factory)
        draft = self.draft("both", snp=["contamination"])
        draft["scientific_settings"] = {"snp-call": {"max_depth": 1500}}
        prepared = prepare_analysis(draft, self.layout)
        job = manager.start(prepared)
        result = manager.wait(job["id"], 10)
        self.assertEqual(result["status"], "planned", result)
        self.assertRegex(result["run_id"], r"^analysis-\d{8}-\d{6}-[a-f0-9]{8}$")
        directory = self.layout.runs_dir / result["run_id"]
        metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        gui = json.loads((directory / "gui.json").read_text(encoding="utf-8"))
        plan = json.loads((directory / "work/engine-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["parameters"]["analyses_by_marker"], {"DNP": [], "SNP": ["contamination"]})
        self.assertEqual(gui["name"], draft["name"])
        self.assertEqual(gui["draft"]["scientific_settings"]["snp-call"]["max_depth"], 1500)
        self.assertFalse(any(s["id"] == "dnp_contamination" for s in plan["steps"]))
        self.assertEqual(manager.active(), {"active": False, "jobs": []})

    def test_cancel_during_final_input_verification_is_recorded(self):
        verifying = threading.Event()
        release = threading.Event()
        verify = DockerComposeRunner._verify_inputs

        def pause_after_check(runner, phase):
            verify(runner, phase)
            if phase == "after_execution":
                verifying.set()
                self.assertTrue(release.wait(5))

        def factory(prepared, job):
            runner = GuiRunner(prepared, job)
            runner.dry_run = True
            return runner

        manager = JobManager(runner_factory=factory, reconcile=lambda *_a, **_k: {"containers": []})
        with patch.object(DockerComposeRunner, "_verify_inputs", pause_after_check):
            job = manager.start(prepare_analysis(self.draft(), self.layout))
            try:
                self.assertTrue(verifying.wait(5))
                self.assertEqual(manager.cancel(job["id"])["status"], "cancel_requested")
            finally:
                release.set()
                result = manager.wait(job["id"], 5)
        self.assertEqual(result["status"], "interrupted", result)
        metadata = json.loads((self.layout.runs_dir / result["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "interrupted")

    def test_final_result_closes_cancellation_before_saving_and_keeps_job_active(self):
        from nipat.execution.tracking import RunRecord
        save = RunRecord.save
        for expected in ("succeeded", "failed"):
            with self.subTest(expected=expected):
                saving = threading.Event()
                release = threading.Event()

                def pause_before_final_save(record):
                    if record.data["finished_at"] and not saving.is_set():
                        saving.set()
                        self.assertTrue(release.wait(5))
                    save(record)

                class LocalRunner(GuiRunner):
                    def _prepare_runtime(self):
                        if expected == "failed":
                            raise RuntimeExecutionError("runtime unavailable")

                    def _record_resource_snapshot(self):
                        pass

                    def _describe_bundled_engine(self):
                        self._image_id = "sha256:" + "1" * 64

                    def _run_command(self, command, *, working_dir=None):
                        output = self.last_run_dir / "output" / "workflow"
                        output.mkdir()
                        steps = self._record.data["parameters"]["plan"]["steps"]
                        state = {"schema_version": 1, "interface": "workflow-plan-execution-v2",
                                 "status": "succeeded",
                                 "steps": [{**step, "status": "succeeded"} for step in steps]}
                        (output / "workflow-state.json").write_text(json.dumps(state), encoding="utf-8")

                manager = JobManager(runner_factory=LocalRunner)
                with patch.object(RunRecord, "save", pause_before_final_save):
                    job = manager.start(prepare_analysis(self.draft(), self.layout))
                    try:
                        self.assertTrue(saving.wait(5))
                        self.assertEqual(manager.get(job["id"])["status"], "finalizing")
                        self.assertTrue(manager.active()["active"])
                        requested = manager.cancel(job["id"])
                        self.assertEqual(requested["status"], "finalizing")
                        self.assertFalse(requested["cancel_requested"])
                    finally:
                        release.set()
                        result = manager.wait(job["id"], 5)
                self.assertEqual(result["status"], expected, result)
                metadata = self.layout.runs_dir / result["run_id"] / "run.json"
                self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["status"], expected)
                self.assertFalse(manager.active()["active"])

    def test_cancel_before_a_container_exists_records_interruption(self):
        entered = threading.Event()
        class SlowRunner(GuiRunner):
            def _prepare_runtime(self):
                entered.set()
                self.job.cancel_event.wait(5)
                self._cancel_point()
        manager = JobManager(runner_factory=SlowRunner, reconcile=lambda *a, **k: {"containers": []})
        job = manager.start(prepare_analysis(self.draft(), self.layout))
        self.assertTrue(entered.wait(5))
        manager.cancel(job["id"])
        result = manager.wait(job["id"], 5)
        self.assertEqual(result["status"], "interrupted", result)
        metadata = json.loads((self.layout.runs_dir / result["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "interrupted")

    def test_cancel_only_stops_a_positively_owned_container(self):
        running = threading.Event()
        stopped = threading.Event()
        class BlockingRunner(GuiRunner):
            def _prepare_runtime(self): pass
            def _record_resource_snapshot(self): pass
            def _describe_bundled_engine(self): self._image_id = "sha256:" + "1" * 64
        def fake_run(runner, *_args, **_kwargs):
            running.set()
            self.assertTrue(stopped.wait(7), "cancel did not stop owned container")
            raise RuntimeExecutionError("container stopped")
        calls = []
        def reconcile(runner, directory, *, stop=False):
            calls.append(stop)
            if stop:
                stopped.set()
            return {"containers": [{"owned": True, "state": "running",
                                    "cleanup": {"status": "removed"} if stop else {}}]}
        manager = JobManager(runner_factory=BlockingRunner, reconcile=reconcile)
        with patch.object(DockerComposeRunner, "run", fake_run):
            job = manager.start(prepare_analysis(self.draft(), self.layout))
            self.assertTrue(running.wait(5))
            manager.cancel(job["id"])
            result = manager.wait(job["id"], 8)
        self.assertEqual(result["status"], "interrupted", result)
        self.assertEqual(calls, [False, True])
        metadata = json.loads((self.layout.runs_dir / result["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "interrupted")

    def test_cancel_retries_when_runtime_has_not_confirmed_stop(self):
        running = threading.Event()
        stopped = threading.Event()
        class BlockingRunner(GuiRunner):
            def _prepare_runtime(self): pass
            def _record_resource_snapshot(self): pass
            def _describe_bundled_engine(self): self._image_id = "sha256:" + "1" * 64
        def fake_run(runner, *_args, **_kwargs):
            running.set()
            self.assertTrue(stopped.wait(8), "unconfirmed cancellation was not retried")
            raise RuntimeExecutionError("container stopped")
        attempts = []
        def reconcile(runner, directory, *, stop=False):
            cleanup = {}
            if stop:
                attempts.append(stop)
                cleanup = {"status": "not_confirmed" if len(attempts) == 1 else "removed"}
                if len(attempts) == 2:
                    stopped.set()
            return {"containers": [{"owned": True, "state": "running", "cleanup": cleanup}]}
        manager = JobManager(runner_factory=BlockingRunner, reconcile=reconcile)
        with patch.object(DockerComposeRunner, "run", fake_run):
            job = manager.start(prepare_analysis(self.draft(), self.layout))
            self.assertTrue(running.wait(5))
            manager.cancel(job["id"])
            result = manager.wait(job["id"], 9)
        self.assertEqual(result["status"], "interrupted", result)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(any("riprovo" in line for line in result["logs"]))

    def test_runtime_failure_never_becomes_successful_gui_result(self):
        class FailingRunner(GuiRunner):
            def _prepare_runtime(self):
                raise RuntimeExecutionError("runtime unavailable")
        manager = JobManager(runner_factory=FailingRunner)
        job = manager.start(prepare_analysis(self.draft(), self.layout))
        result = manager.wait(job["id"], 5)
        self.assertEqual(result["status"], "failed")
        self.assertIn("runtime unavailable", result["error"])
        metadata = json.loads((self.layout.runs_dir / result["run_id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["status"], "failed")

    def test_next_ordinary_job_in_same_gui_starts_vm_before_any_docker_command(self):
        image = "sha256:" + "1" * 64
        guest_running = True
        starts = []
        launched = []
        class LocalRunner(GuiRunner):
            def _capture_process(runner, command, **kwargs):
                nonlocal guest_running
                if command == ["fixture-lima", "ensure"]:
                    starts.append(guest_running)
                    guest_running = True
                    return ""
                self.assertTrue(guest_running)
                if command[:2] == ["docker", "info"]:
                    return "linux"
                if "config" in command:
                    return json.dumps({"services": {"scientific": {"image": image}}})
                if "inspect" in command:
                    return json.dumps({"id": image, "os": "linux", "architecture": "arm64"})
                self.assertEqual(command[:2], ["docker", "run"])
                return "test runtime"

            def _run_command(runner, command, *, working_dir=None):
                nonlocal guest_running
                launched.append(runner.last_run_dir)
                if len(launched) == 1:
                    guest_running = False
                    raise RuntimeInterruptedError("VM stopped")
                output = runner.last_run_dir / "output" / "workflow"
                output.mkdir()
                steps = runner._record.data["parameters"]["plan"]["steps"]
                (output / "workflow-state.json").write_text(json.dumps({
                    "schema_version": 1, "interface": "workflow-plan-execution-v2", "status": "succeeded",
                    "steps": [dict(step, status="succeeded") for step in steps],
                }))

        class LocalTransport(DockerTransport):
            backend = "lima"
            metadata = {"backend": "lima", "lima_instance": "nipat", "lima_home": str(self.root)}
            def ensure_command(self):
                return ["fixture-lima", "ensure"]

        manager = JobManager(runner_factory=LocalRunner)
        with (patch.object(DockerTransport, "from_environment", return_value=LocalTransport()),
              patch("nipat.execution.runner.platform.machine", return_value="arm64"),
              patch.object(GuiRunner, "_record_resource_snapshot"),
              patch.object(GuiRunner, "_describe_bundled_engine")):
            prepared = prepare_analysis(self.draft(), self.layout)
            first = manager.wait(manager.start(prepared)["id"], 5)
            self.assertEqual(first["status"], "interrupted", first)
            previous = self.layout.runs_dir / first["run_id"] / "run.json"
            before = previous.read_bytes()
            second = manager.wait(manager.start(prepared)["id"], 5)
        self.assertEqual(second["status"], "succeeded", second)
        self.assertEqual(starts, [True, False])
        self.assertEqual(launched, [previous.parent, self.layout.runs_dir / second["run_id"]])
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(previous.read_bytes(), before)
        self.assertFalse(json.loads(before)["execution_options"]["performance_diagnostics"])


class GuiPrepareTests(GuiRuntimeFixture):
    def completed_caller(self, *, gui=False, status="succeeded", count=4):
        directory = self.layout.runs_dir / "previous"
        directory.mkdir(parents=True)
        mapping, artifacts = [], []
        # The native filename order deliberately differs from biological order.
        for index, sample in enumerate(list(reversed(self.samples))[:count], 1):
            identifier = sample["id"]
            relative = f"output/individual_outputs/full_output_sample_{index:04d}.txt"
            destination = directory / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            original = next(row for row in self.tables["DNP"] if row["id"] == identifier)
            destination.write_bytes(Path(original["path"]).read_bytes())
            mapping.append({"sample_id": identifier, "biological_id": identifier,
                            "original_path": sample["path"]})
            artifacts.append({"path": relative, "sample": identifier,
                              "native_name": f"sample_{index:04d}",
                              "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
        metadata = {"schema_version": 1, "workflow": "dnp-call", "run_name": "Previous",
                    "status": status, "parameters": {"panel": str(self.dnp_panel),
                        "sample_mapping": mapping, "scientific_settings_effective": {
                            "contamination": {"include_zero": False}}}, "execution_options": {"max_workers": 2}}
        (directory / "run.json").write_text(json.dumps(metadata))
        work = directory / "work"
        work.mkdir()
        (work / "scientific-validation.json").write_text(json.dumps({"schema_version": 1,
            "workflow": "dnp-call", "status": "passed", "artifacts": {"dnp-tables": artifacts}}))
        if gui:
            draft = self.draft("dnp", ["cpi", "cpin"])
            draft["scientific_settings"] = {"cpin": {"min_child_reads": 7, "site_selection": "other_allele",
                                                       "err_const_snp": 0.003}}
            (directory / "gui.json").write_text(json.dumps({"schema_version": 1,
                "name": "Original GUI experiment", "draft": draft}))
        return directory

    def test_legacy_call_outputs_prepare_only_requested_analysis_with_exact_identities(self):
        directory = self.completed_caller()
        before = {str(path): path.read_bytes() for path in directory.rglob("*") if path.is_file()}
        draft = self.service().call("run.prepare", {"run_id": "previous", "module": "contamination"})
        self.assertEqual(draft["caller"], "tables")
        self.assertEqual(draft["branches"], {"DNP": ["contamination"], "SNP": []})
        self.assertEqual(draft["families"], {"cpi": [], "cpin": []})
        self.assertEqual(draft["samples"][0]["id"], "Child")
        self.assertTrue(draft["samples"][0]["path"].endswith("full_output_sample_0001.txt"))
        self.assertFalse(draft["scientific_settings"]["contamination"]["include_zero"])
        self.assertEqual(draft["execution"], {"max_workers": 2})
        prepared = prepare_analysis(draft, self.layout)
        self.assertEqual([step["workflow"] for step in prepared.preview["steps"]], ["contamination"])
        self.assertTrue(all(row["kind"] == "dnp-table" for row in draft["samples"]))
        self.assertEqual(before, {str(path): path.read_bytes() for path in directory.rglob("*") if path.is_file()})

    def test_gui_followup_keeps_compatible_family_resources_settings_and_no_prior_steps(self):
        self.completed_caller(gui=True)
        draft = self.service().run_prepare("previous", "cpin")
        self.assertEqual(draft["families"]["cpin"], [{"id": "Postnatal", "mother": "Mother", "father": "Father", "child": "Child"}])
        self.assertEqual(draft["families"]["cpi"], [])
        for settings in (draft["scientific_settings"]["cpin"],
                         self.service().run_reuse("previous")["scientific_settings"]["cpin"]):
            self.assertNotIn("min_child_reads", settings)
            self.assertIsNone(settings.get("min_coverage"))
            self.assertEqual(settings["mismatch_probability_snp"], 0.003)
            self.assertTrue(settings["include_hom_het"])
            self.assertFalse(any(settings[key] for key in ("include_hom_hom", "include_het_het", "include_het_hom")))
        self.assertEqual(draft["resources"]["DNP"]["popfreq"], str(self.dnp_freq))
        prepared = prepare_analysis(draft, self.layout)
        self.assertEqual([step["workflow"] for step in prepared.preview["steps"]], ["cpin"])

    def test_fetal_followup_offers_verified_caller_tables_without_assigning_a_mother(self):
        self.completed_caller(gui=True)
        draft = self.service().run_prepare("previous", "fetal-sex")
        self.assertEqual(draft["caller"], "tables")
        self.assertEqual(draft["fetal_sex"], {"id": "", "source": "sample-tables", "dnp": "", "y": ""})
        self.assertEqual({r["kind"] for r in draft["samples"]}, {"dnp-table"})
        self.assertEqual({r["id"] for r in draft["samples"]}, {"Child", "Mother", "Father", "Plasma"})
        self.assertTrue(all(Path(r["path"]).is_file() for r in draft["samples"]))

    def test_incomplete_or_unidentified_counts_do_not_silently_restart_callers(self):
        directory = self.completed_caller(status="failed")
        with self.assertRaisesRegex(ValidationError, "conteggi completi"):
            self.service().run_prepare("previous", "cpi")
        data = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        data["status"] = "succeeded"
        (directory / "run.json").write_text(json.dumps(data))
        (directory / "work/scientific-validation.json").unlink()
        with self.assertRaisesRegex(ValidationError, "conteggi completi"):
            self.service().run_prepare("previous", "cpi")
        with self.assertRaises(ValidationError):
            self.service().run_prepare("previous", "dnp-call")

    def test_tables_only_followup_reuses_original_counts_without_any_caller_output(self):
        def factory(prepared, job):
            runner = GuiRunner(prepared, job)
            runner.dry_run = True
            return runner
        manager = JobManager(runner_factory=factory)
        started = manager.start(prepare_analysis(self.draft("tables", snp=["cpi"]), self.layout))
        previous = manager.wait(started["id"], 5)
        self.assertEqual(previous["status"], "planned", previous)
        draft = self.service().run_prepare(previous["run_id"], "contamination")
        self.assertEqual(draft["samples"], self.tables["SNP"])
        self.assertEqual(draft["branches"], {"DNP": [], "SNP": ["contamination"]})
        self.assertEqual(draft["families"], {"cpi": [], "cpin": []})
        prepared = prepare_analysis(draft, self.layout)
        self.assertEqual([step["workflow"] for step in prepared.preview["steps"]], ["contamination"])

        table = Path(draft["samples"][0]["path"])
        original = table.read_text(encoding="utf-8")
        changed = original.replace("50\t50", "49\t51")
        self.assertNotEqual(changed, original)
        table.write_text(changed, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tabella dei conteggi"):
            self.service().run_prepare(previous["run_id"], "contamination")

    def test_followup_checks_archived_counts_in_one_inventory_and_accepts_older_unhashed_records(self):
        directory = self.completed_caller()
        service = self.service()
        store = service._results()
        with patch.object(store, "_file_descriptors", wraps=store._file_descriptors) as scan:
            draft = service.call("run.prepare", {"run_id": "previous", "module": "contamination"})
        self.assertEqual(len(draft["samples"]), 4)
        self.assertEqual(scan.call_count, 1)
        target = Path(draft["samples"][0]["path"])
        rows = target.read_text(encoding="utf-8")
        changed = rows.replace("50\t50", "51\t49")
        self.assertNotEqual(changed, rows)
        target.write_text(changed, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "tabella dei conteggi"):
            service.call("run.prepare", {"run_id": "previous", "module": "contamination"})

        target.unlink()
        with self.assertRaisesRegex(ValueError, "non è disponibile"):
            service.call("run.prepare", {"run_id": "previous", "module": "contamination"})
        target.write_text(changed, encoding="utf-8")

        recorded = directory / "work/scientific-validation.json"
        validation = json.loads(recorded.read_text(encoding="utf-8"))
        for entry in validation["artifacts"]["dnp-tables"]:
            del entry["sha256"]
        recorded.write_text(json.dumps(validation), encoding="utf-8")
        old = service.call("run.prepare", {"run_id": "previous", "module": "contamination"})
        self.assertEqual(old, draft)
        preview = service.call("plan.preview", {"draft": old})
        self.assertEqual([step["workflow"] for step in preview["steps"]], ["contamination"])

        # Some legacy runs record only a subset of per-sample outputs.
        legacy_entry = validation["artifacts"]["dnp-tables"].pop()
        (directory / legacy_entry["path"]).unlink()
        recorded.write_text(json.dumps(validation), encoding="utf-8")
        partial_mapping = service.call("run.prepare", {"run_id": "previous", "module": "contamination"})
        self.assertEqual({row["id"] for row in partial_mapping["samples"]},
                         {row["id"] for row in old["samples"]} - {legacy_entry["sample"]})

    def test_reuse_and_derived_plans_keep_requested_limits_even_without_gui_snapshot(self):
        def factory(prepared, job):
            runner = GuiRunner(prepared, job)
            runner.dry_run = True
            return runner

        source = self.draft("tables", snp=["cpi"])
        source["name"] = "X" * 150
        source["execution"] = {"cpus": None, "memory_mb": None, "max_workers": 3, "dnp_block_loci": 40}
        source["scientific_settings"] = {"cpi": {"min_fetal_reads": 6}}
        manager = JobManager(runner_factory=factory)
        prepared = prepare_analysis(source, self.layout)
        job = manager.start(prepared)
        original_run = manager.wait(job["id"], 5)
        self.assertEqual(original_run["status"], "planned", original_run)
        run_id = original_run["run_id"]
        directory = self.layout.runs_dir / run_id
        path = directory / "run.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        requested = metadata["execution_options"]
        metadata["execution_options"] = {**requested, "cpus": 1, "memory_mb": 1024}
        metadata["concurrent_execution"] = {"requested_options": requested, "participants_at_admission": 4,
                                            "assigned_cpus": 1, "assigned_memory_mib": 1024}
        path.write_text(json.dumps(metadata), encoding="utf-8")
        service = self.service()
        service.ui_save({**service.ui_get(), "language": "en"})
        for with_gui in (True, False):
            with self.subTest(with_gui=with_gui):
                if not with_gui:
                    (directory / "gui.json").unlink()
                self.assertEqual(service.call("runs.get", {"run_id": run_id})["execution"], metadata["execution_options"])
                repeat = service.call("run.reuse", {"run_id": run_id})
                self.assertTrue(repeat["name"].endswith(" · new analysis"))
                self.assertLessEqual(len(repeat["name"]), 120)
                rerun = service.call("plan.preview", {"draft": repeat})
                self.assertEqual(rerun["execution"], requested)
                self.assertEqual(rerun["steps"], prepared.preview["steps"])
                followup = service.call("run.prepare", {"run_id": run_id, "module": "contamination"})
                self.assertTrue(followup["name"].endswith(" · contamination"))
                self.assertLessEqual(len(followup["name"]), 120)
                followup["resources"]["SNP"]["contamination_panel"] = str(self.snp_panel)
                next_preview = service.call("plan.preview", {"draft": followup})
                self.assertEqual(next_preview["execution"], requested)
                self.assertEqual([step["workflow"] for step in next_preview["steps"]], ["contamination"])
