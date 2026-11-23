"""Desktop adapters preserve caller selection, validated plans and recorded outcomes."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import io
import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from nipat.errors import RuntimeExecutionError, ValidationError
from nipat.execution.progress import ProgressSnapshot
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.transport import DockerTransport
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
        project = self.root / "project"
        project.mkdir()
        (project / "compose.yaml").write_text("services: {}\n")
        self.layout = ProjectLayout(project, self.root, self.root / "data", self.root / "runs", project / "compose.yaml")
        self.store = PreferencesStore(self.root / "settings" / "preferences.json")
        self.samples = [{"id": name, "path": str(self.file(name + " with spaces.bam", name)), "kind": "bam"}
                        for name in ("Plasma", "Mother", "Father", "Child")]
        self.reference = self.file("ref.fa", ">chr1\nACGT\n")
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
        runner = DockerComposeRunner(self.layout, dry_run=True)
        run = Workflows(self.layout, runner).analyze(
            caller="snp", analyses=[], samples=[("Plasma", bam)], reference=self.reference,
            snp_panel=self.snp_panel, dnp_tables=[("Other", Path(self.tables["DNP"][0]["path"]))],
            dnp_analyses=["contamination"], dnp_contamination_panel=self.dnp_panel, run_name="cli-igv")
        service = self.service()
        self.assertTrue(service.call("runs.get", {"run_id": run.name})["has_igv_inputs"])
        self.assertEqual(service.call("run.igv", {"run_id": run.name}), {
            "reference": {"fasta": str(self.reference), "index": ""},
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
        self.assertEqual(set(value["settings"]["workflows"]), {"dnp-call", "snp-call", "contamination", "cpi", "cpin"})
        self.assertEqual(sum(len(w["parameters"]) for w in value["settings"]["workflows"].values()), 45)
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
            def _prepare_runtime(self):
                both_running.wait(timeout=5)
                while not release.wait(.02):
                    self._cancel_point()
                self._cancel_point()
                raise RuntimeExecutionError("end of second fixture")
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
        self.assertEqual(other["status"], "failed")
        self.assertTrue(service.call("runs.remove", {"run_id": other["run_id"]})["outputs_preserved"])
        self.assertEqual(manager.list(), [])
        self.assertEqual(service.call("runs.list")["total"], 0)

    def test_overlap_container_limits_use_guest_share_without_raising_explicit_limits(self):
        from nipat.execution.options import ExecutionOptions
        prepared = prepare_analysis(self.draft(), self.layout)
        for count, requested, expected in [
            (1, ExecutionOptions(), (None, None)),
            (2, ExecutionOptions(), (2, 2048)),
            (2, ExecutionOptions(cpus=1, memory_mb=1024), (1, 1024)),
        ]:
            with self.subTest(count=count, options=requested):
                job = Job(replace(prepared, execution=requested), count)
                runner = GuiRunner(job.prepared, job)
                runner._record = Mock(data={})
                snapshot = {"runtime": {"effective": {"cpus": 4, "memory_mib": 4096}}}
                with patch("nipat.resources.ResourceManager.snapshot", return_value=snapshot):
                    runner._record_resource_snapshot()
                self.assertEqual((runner.options.cpus, runner.options.memory_mb), expected)
                if count > 1:
                    self.assertEqual(runner.options.compose_limits()["mem_limit"], expected[1] * 1024**2)
                    self.assertEqual(runner._record.data["concurrent_execution"]["requested_options"], requested.as_dict())
                else:
                    self.assertNotIn("concurrent_execution", runner._record.data)

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
            draft["scientific_settings"] = {"cpin": {"min_child_reads": 7}}
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
        self.assertEqual(draft["scientific_settings"]["cpin"]["min_child_reads"], 7)
        self.assertEqual(draft["resources"]["DNP"]["popfreq"], str(self.dnp_freq))
        prepared = prepare_analysis(draft, self.layout)
        self.assertEqual([step["workflow"] for step in prepared.preview["steps"]], ["cpin"])

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
