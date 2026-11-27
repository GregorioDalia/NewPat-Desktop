from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from newpat_scientific.errors import ValidationError
from newpat_scientific.executor import PlanExecutionError, execute_plan
from snp_output_helpers import write_snp_auxiliary


@unittest.skipUnless(os.name == "posix", "scientific execution runs inside the Linux image")
class SnpWorkflowExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="nipat-snp-plan-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.inputs = self.root / "original inputs $ ,="
        self.inputs.mkdir()
        self.bam = self.inputs / "sample_0001.bam"
        self.bam.write_bytes(b"fixture bam")
        self.reference = self.inputs / "reference.fa"
        self.reference.write_text(">chr1\nAAAAAAAAAAAAAAAAAAAA\n", encoding="utf-8")
        Path(str(self.reference) + ".fai").write_text("chr1\t20\t6\t20\t21\n", encoding="utf-8")
        self.panel = self.inputs / "snp panel.tsv"
        self.panel.write_text("pos\tref\talt\nchr1:10\tA\tG\nchr1:15\tA\tT\n", encoding="utf-8")
        self.pileup = self.inputs / "pileup.txt"
        self.pileup.write_text("chr1\t10\tA\t2\t.G\tII\tread1,read2\n", encoding="utf-8")
        self.script = self.root / "SNPcall.R"
        self.script.write_text("# unchanged R\n", encoding="utf-8")
        self.run = self.root / "workflow"
        self.plan = {"schema_version": 1, "samples": [
            {"id": "donor", "kind": "bam", "path": str(self.bam)},
        ], "steps": [{"id": "snp", "workflow": "snp-call", "inputs": {
            "sample": "donor", "reference": str(self.reference), "panel": str(self.panel),
        }, "parameters": {"mode": "bam"}}]}
        self.calls = []

    @staticmethod
    def write_bam_header(command, log):
        Path(command[command.index("-o") + 1]).write_text("@SQ\tSN:chr1\tLN:20\n", encoding="utf-8")
        log.write_text("samtools header\n", encoding="utf-8")
        return 0

    def execute(self, process=None):
        return execute_plan(self.plan, run_dir=self.run, script_paths={"snp-call": self.script},
                            run_process=process or self.fake_process)

    def fake_process(self, command, cwd, log):
        self.calls.append(command)
        if command[:2] == ["samtools", "view"]:
            return self.write_bam_header(command, log)
        log.write_text("samtools output\n" if command[0] == "samtools" else "R output\n", encoding="utf-8")
        if command[0] == "samtools":
            Path(command[command.index("-o") + 1]).write_bytes(self.pileup.read_bytes())
        else:
            Path(command[command.index("--out") + 1]).write_text(
                "chr\tpos\tREF\tALT\tN_REF\tN_ALT\tN_Other\ttotal_count\tratio\tGL0\tGL1\tGL2\tGT\treads_discarded_for_indels\tratio_reads_discarded_for_indels\tcombined_bases\tcombined_counts\n"
                "chr1\t10\tA\tG\t1\t1\t0\t2\t0.5\t-9.21\t-1.386\t-9.21\t0/1\t0\t0\tA-G\t1-1\n"
                "chr1\t15\tA\tT\t0\t0\t0\t0\tNA\tNA\tNA\tNA\tNA\tNA\tNA\tNA\tNA\n", encoding="utf-8",
            )
            write_snp_auxiliary(Path(command[command.index("--out") + 1]).parent)
        return 0

    def imported_pileup(self):
        self.plan["samples"][0].update(kind="snp-pileup", path=str(self.pileup))
        self.plan["steps"][0]["inputs"]["reference"] = None
        self.plan["steps"][0]["parameters"]["mode"] = "pileup"

    def add_independent_step(self):
        step = copy.deepcopy(self.plan["steps"][0])
        step["id"] = "zzz_snp"
        self.plan["steps"].append(step)

    def test_bam_prepares_then_runs_r_and_preserves_originals_and_intermediates(self):
        before = {path.name: path.read_bytes() for path in self.inputs.iterdir()}
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual([call[0] for call in self.calls], ["samtools", "samtools", "Rscript"])
        self.assertEqual(self.calls[0][:4], ["samtools", "view", "--no-PG", "-H"])
        self.assertEqual(self.calls[0][-1], str(self.bam))
        self.assertEqual(result, json.loads((self.run / "workflow-state.json").read_text()))
        record = result["steps"][0]
        self.assertEqual(record["sample_mapping"], {"sample": "donor", "mode": "bam", "path": str(self.bam)})
        self.assertEqual(record["preparation_exit_code"], 0)
        self.assertEqual(record["artifacts"]["snp-tables"][0]["sample"], "donor")
        self.assertEqual(record["artifacts"]["preparation"], record["preparation_artifacts"])
        self.assertEqual([item["kind"] for item in record["preparation_artifacts"]], ["regions-bed", "pileup"])
        for artifact in [*record["preparation_artifacts"], *record["artifacts"]["snp-tables"]]:
            path = self.run / artifact["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), artifact["sha256"])
        self.assertEqual((self.run / "steps/snp/work/snp_regions.bed").read_text(),
                         "chr1\t8\t11\nchr1\t13\t16\n")
        self.assertEqual((self.run / "steps/snp/preparation.log").read_text(), "samtools output\n")
        self.assertEqual((self.run / "steps/snp/command.log").read_text(), "R output\n")
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.inputs.iterdir()})

    def test_snp_progress_has_measured_boundaries_and_original_plan_identity(self):
        events_dir = self.root / "progress"
        with patch.dict(os.environ, {"NIPAT_PROGRESS_DIR": str(events_dir), "NIPAT_PERFORMANCE_DIR": ""}):
            result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        events = [json.loads(line) for path in events_dir.glob("*.jsonl")
                  for line in path.read_text().splitlines()]
        actual = [row for row in events if row["step_id"] == "snp"]
        self.assertEqual({row["phase"] for row in actual}, {
            "preparation", "pileup", "presentation-preparation", "r-execution", "output-validation",
            "presentation-finalization"})
        self.assertTrue(all(row["sample_ids"] == ["donor"] for row in actual))
        self.assertFalse(any("total" in row for row in actual))

    def test_imported_pileup_calls_only_r_and_does_not_claim_generation(self):
        self.imported_pileup()
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual([call[0] for call in self.calls], ["Rscript"])
        self.assertEqual(self.calls[0][self.calls[0].index("--pileup") + 1], str(self.pileup))
        record = result["steps"][0]
        self.assertNotIn("preparation_command", record)
        self.assertNotIn("preparation_artifacts", record)
        self.assertEqual(record["artifacts"]["preparation"], [])
        self.assertFalse((self.run / "steps/snp/work/pileup.txt").exists())
        self.assertFalse((self.run / "steps/snp/preparation.log").exists())

    def test_duplicate_panel_coordinates_fail_before_execution(self):
        self.imported_pileup()
        with self.panel.open("a", encoding="utf-8") as handle:
            handle.write("chr1:10\tA\tG\n")
        with self.assertRaisesRegex(ValidationError, "duplicata"):
            self.execute()
        self.assertFalse(self.run.exists())
        self.assertEqual(self.calls, [])

    def test_zero_count_na_remains_supported(self):
        self.imported_pileup()
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        output = self.run / result["steps"][0]["artifacts"]["snp-tables"][0]["path"]
        self.assertIn("chr1\t15\tA\tT\t0\t0\t0\t0\tNA", output.read_text())

    def test_external_input_errors_prevent_all_execution_and_directory_creation(self):
        original = copy.deepcopy(self.plan)
        for mutation in ("reference_missing", "index_missing", "bgzf_index_missing", "bad_panel", "bad_pileup"):
            with self.subTest(mutation=mutation):
                self.plan = copy.deepcopy(original)
                self.run = self.root / mutation
                self.reference.write_text(">chr1\nAAAA\n", encoding="utf-8")
                Path(str(self.reference) + ".fai").write_text("index", encoding="utf-8")
                self.panel.write_text("pos\tref\talt\nchr1:10\tA\tG\n", encoding="utf-8")
                if mutation == "reference_missing":
                    self.reference.unlink()
                elif mutation == "index_missing":
                    Path(str(self.reference) + ".fai").unlink()
                elif mutation == "bgzf_index_missing":
                    reference = self.inputs / "reference.fa.gz"
                    reference.write_bytes(b"compressed")
                    Path(str(reference) + ".fai").write_text("index", encoding="utf-8")
                    self.plan["steps"][0]["inputs"]["reference"] = str(reference)
                elif mutation == "bad_panel":
                    self.panel.write_text("pos\tref\talt\nchr1:1\tA\tG\n", encoding="utf-8")
                else:
                    self.imported_pileup()
                    self.pileup.write_text("chr1\t10\tA\t2\t.G\tII\n", encoding="utf-8")
                with self.assertRaises(ValidationError):
                    self.execute()
                self.assertFalse(self.run.exists())
                self.assertEqual(self.calls, [])

    def test_later_invalid_independent_step_prevents_earlier_valid_step(self):
        self.add_independent_step()
        self.plan["steps"][1]["inputs"]["panel"] = str(self.inputs / "missing.tsv")
        with self.assertRaises(ValidationError):
            self.execute()
        self.assertFalse(self.run.exists())
        self.assertEqual(self.calls, [])

    def test_samtools_failure_preserves_log_without_running_r_or_next_step(self):
        self.add_independent_step()
        for failing_command, expected_calls in (("view", ["view"]), ("mpileup", ["view", "mpileup"])):
            with self.subTest(command=failing_command):
                self.calls.clear()
                self.run = self.root / f"failure_{failing_command}"

                def fail(command, cwd, log):
                    if command[:2] == ["samtools", failing_command]:
                        self.calls.append(command)
                        log.write_text("samtools failed", encoding="utf-8")
                        return 23
                    return self.fake_process(command, cwd, log)

                result = self.execute(fail)
                self.assertEqual(result, json.loads((self.run / "workflow-state.json").read_text()))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["exit_code"], 23)
                self.assertEqual([s["status"] for s in result["steps"]], ["failed", "blocked"])
                self.assertEqual([call[1] for call in self.calls], expected_calls)
                failed = result["steps"][0]
                self.assertEqual(failed["preparation_exit_code"], 23)
                self.assertEqual(failed["preparation_command"], self.calls[-1])
                self.assertEqual((self.run / failed["preparation_log"]).read_text(), "samtools failed")
                self.assertTrue((self.run / failed["request"]).exists())
                self.assertFalse((self.run / failed["log"]).exists())
                self.assertFalse((self.run / "steps/zzz_snp").exists())

    def test_zero_exit_with_missing_or_invalid_generated_pileup_prevents_r(self):
        for content in (None, "chr1\t10\tA\t1\t.\tI\n"):
            with self.subTest(content=content):
                self.run = self.root / f"invalid_{len(self.calls)}"
                def invalid(command, cwd, log):
                    self.calls.append(command)
                    if command[:2] == ["samtools", "view"]:
                        return self.write_bam_header(command, log)
                    log.write_text("preparation finished", encoding="utf-8")
                    if content is not None:
                        Path(command[command.index("-o") + 1]).write_text(content, encoding="utf-8")
                    return 0
                result = self.execute(invalid)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["exit_code"], 2)
                self.assertTrue(all(call[0] == "samtools" for call in self.calls))
                self.assertFalse((self.run / "steps/snp/command.log").exists())

    def test_empty_generated_pileup_retains_every_panel_locus_as_unassigned(self):
        def empty(command, cwd, log):
            code = self.fake_process(command, cwd, log)
            if command[:2] == ["samtools", "mpileup"]:
                Path(command[command.index("-o") + 1]).write_text("")
            elif command[0] == "Rscript":
                table = Path(command[command.index("--out") + 1])
                header = table.read_text().splitlines()[0]
                table.write_text(header + "\n" + "\n".join(
                    f"chr1\t{position}\tA\t{alt}\t0\t0\t0\t0\tNA\tNA\tNA\tNA\tNA\tNA\tNA\tNA\tNA"
                    for position, alt in ((10, "G"), (15, "T"))) + "\n")
                write_snp_auxiliary(table.parent)
            return code
        result = self.execute(empty)
        self.assertEqual(result["status"], "succeeded", result.get("error"))
        self.assertEqual([call[0] for call in self.calls], ["samtools", "samtools", "Rscript"])
        self.assertEqual(result["steps"][0]["artifacts"]["quality_warnings"], [])
        self.assertEqual((self.run / "steps/snp/work/pileup.txt").stat().st_size, 0)

    def test_preparation_cancellation_blocks_other_independent_steps(self):
        self.add_independent_step()
        def cancel(command, cwd, log):
            code = self.fake_process(command, cwd, log)
            if command[:2] == ["samtools", "mpileup"]:
                signal.raise_signal(signal.SIGTERM)
            return code
        result = self.execute(cancel)
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["exit_code"], 143)
        self.assertEqual([s["status"] for s in result["steps"]], ["cancelled", "blocked"])
        self.assertEqual([call[1] for call in self.calls], ["view", "mpileup"])
        self.assertFalse((self.run / "steps/snp/command.log").exists())

    def test_r_failure_keeps_generated_artifacts_and_does_not_start_next_step(self):
        self.add_independent_step()
        def fail_r(command, cwd, log):
            if command[0] == "samtools":
                return self.fake_process(command, cwd, log)
            self.calls.append(command)
            log.write_text("R error", encoding="utf-8")
            return 17
        result = self.execute(fail_r)
        self.assertEqual(result["exit_code"], 17)
        self.assertEqual([s["status"] for s in result["steps"]], ["failed", "blocked"])
        self.assertEqual(len(result["steps"][0]["preparation_artifacts"]), 2)
        self.assertEqual(result["steps"][0]["artifacts"], {})

    def test_r_cancellation_keeps_preparation_and_sample_identity(self):
        self.add_independent_step()
        def cancel_r(command, cwd, log):
            self.fake_process(command, cwd, log)
            if command[0] == "Rscript":
                raise KeyboardInterrupt
            return 0
        result = self.execute(cancel_r)
        self.assertEqual(result["exit_code"], 130)
        self.assertEqual([s["status"] for s in result["steps"]], ["cancelled", "blocked"])
        record = result["steps"][0]
        self.assertEqual(record["sample_mapping"]["sample"], "donor")
        self.assertEqual(len(record["preparation_artifacts"]), 2)
        self.assertEqual(record["artifacts"], {})
        self.assertFalse((self.run / "steps/zzz_snp").exists())

    def test_missing_malformed_or_unrelated_results_are_not_successful(self):
        self.imported_pileup()
        for mutation in ("missing", "header_only", "column_missing", "duplicate_column", "short_row", "wrong_locus", "outside"):
            with self.subTest(mutation=mutation):
                self.run = self.root / mutation
                def corrupt(command, cwd, log):
                    self.fake_process(command, cwd, log)
                    output = Path(command[command.index("--out") + 1])
                    text = output.read_text()
                    if mutation == "missing":
                        output.unlink()
                    elif mutation == "header_only":
                        output.write_text(text.splitlines()[0] + "\n")
                    elif mutation == "column_missing":
                        output.write_text(text.replace("N_Other", "unknown"))
                    elif mutation == "duplicate_column":
                        output.write_text(text.replace("\tratio\tGL0", "\tratio\tratio"))
                    elif mutation == "short_row":
                        output.write_text(text + "chr1\t10\n")
                    elif mutation == "wrong_locus":
                        output.write_text(text.replace("chr1\t15\t", "chr2\t15\t"))
                    else:
                        external = self.inputs / "outside.txt"
                        external.write_text(text)
                        output.unlink()
                        output.symlink_to(external)
                    return 0
                result = self.execute(corrupt)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["error"]["code"], "execution.output")

    def test_multiple_steps_share_one_sample_but_keep_results_separate(self):
        self.add_independent_step()
        result = self.execute()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["execution_order"], ["snp", "zzz_snp"])
        artifacts = [record["artifacts"]["snp-tables"][0] for record in result["steps"]]
        self.assertEqual([artifact["sample"] for artifact in artifacts], ["donor", "donor"])
        self.assertNotEqual(artifacts[0]["path"], artifacts[1]["path"])
        self.assertEqual(artifacts[0]["sha256"], artifacts[1]["sha256"])
        snapshot = {str(path.relative_to(self.run)): path.read_bytes() for path in self.run.rglob("*") if path.is_file()}
        with self.assertRaises(PlanExecutionError):
            self.execute()
        self.assertEqual(snapshot, {str(path.relative_to(self.run)): path.read_bytes() for path in self.run.rglob("*") if path.is_file()})


class SnpQualificationPolicyTests(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import sys
        scripts = Path(__file__).resolve().parents[1] / "scripts"
        self.enterContext(patch.object(sys, "path", [str(scripts), *sys.path]))
        spec = importlib.util.spec_from_file_location("snp_qualification_policy", scripts / "verify_snp_workflow.py")
        self.verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.verifier)
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.outer = self.root / "parallel/snp"
        self.outer.mkdir(parents=True)
        self.budget = {"mode": "auto", "workers": 2, "tasks": 2, "cpu_limit": 4,
                       "memory_worker_limit": 4, "reason": "fixed-capacity-task-budget",
                       "resource_policy": "nipat-fixed-resources-v1",
                       "workload_model": "max-loaded-coordinator-rss-x2-and-module-estimate",
                       "memory_per_worker_mib": 1024}
        self.state = {"snp_parallel": self.budget, "steps": []}
        for number in (1, 2):
            step = {"id": f"snp{number}", "workflow": "snp-call", "status": "succeeded",
                    "work_dir": f"steps/snp{number}/work"}
            self.state["steps"].append(step)
            self.write_inner(step)
        self.write_outer()

    def write_events(self, directory, budget, *, label, workers, coordinator, indices):
        base = {**budget, "schema_version": 1, "interface": "nipat-parallel-v1",
                "coordinator_pid": coordinator, "label": label}
        events = [{**base, "event": "plan", "observed_at_unix": 0}]
        for index in indices:
            process = coordinator + index if workers > 1 else coordinator
            identity = {**base, "pid": process, "task_index": index}
            events.extend([{**identity, "event": "task-start", "observed_at_unix": index},
                           {**identity, "event": "task-end", "observed_at_unix": index + 5,
                            "outcome": "succeeded"}])
        (directory / f"worker-{coordinator}.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")

    def write_outer(self, *, indices=None):
        (self.outer / "budget.json").write_text(json.dumps(self.budget))
        workers = self.budget["workers"]
        if indices is None:
            indices = (1, 2) if workers > 1 else ()
        self.write_events(self.outer, self.budget, label="snp-samples", workers=workers,
                          coordinator=1, indices=indices)

    def write_inner(self, step, *, serial=False, workers=1, nested=True):
        directory = self.root / step["work_dir"] / "parallel"
        directory.mkdir(parents=True, exist_ok=True)
        budget = {"workers": workers, "tasks": 2, "mode": "serial" if serial else "auto",
                  "reason": "requested-serial" if serial else ("shared-budget-child" if nested else "fixed-capacity-task-budget"),
                  "cpu_limit": 4, "memory_worker_limit": 4}
        self.write_events(directory, budget, label="snp-read-groups", workers=workers,
                          coordinator=10, indices=(1, 2))

    def check(self, mode="auto", *, require_inner=True):
        from newpat.experiments.options import ExecutionOptions
        return self.verifier.check_snp_execution_policy(self.root, self.state, count=len(self.state["steps"]),
            options=ExecutionOptions(execution_mode=mode, max_workers=2), require_inner=require_inner)

    def test_parallel_samples_observed_without_nested_workers(self):
        evidence = self.check()
        self.assertTrue(evidence["outer_execution"]["simultaneous_child_workers"])
        self.assertTrue(all(not item["observed_child_pids"] for item in evidence["loaded_r_execution"].values()))
        self.write_inner(self.state["steps"][0], workers=2)
        with self.assertRaisesRegex(ValueError, "budget"):
            self.check()

    def test_weighted_evidence_rejects_overlapping_exclusive_or_over_budget_samples(self):
        self.budget["sample_budget_mib"] = 2048
        self.write_outer()
        estimates = {"snp1": {"charge_mib": 1024, "memory_mib": 1024, "exclusive": False},
                     "snp2": {"charge_mib": 1024, "memory_mib": 1024, "exclusive": False}}
        path = self.outer / "sample-estimates.json"
        path.write_text(json.dumps(estimates))
        self.assertTrue(self.check()["outer_execution"]["simultaneous_child_workers"])
        for patch in ({"exclusive": True, "charge_mib": None, "memory_mib": None},
                      {"charge_mib": 1100}):
            with self.subTest(patch=patch):
                path.write_text(json.dumps({**estimates, "snp1": {**estimates["snp1"], **patch}}))
                with self.assertRaisesRegex(ValueError, "cumulative"):
                    self.check()

    def add_weighted_third_sample(self):
        self.budget.update(sample_budget_mib=2048, tasks=3)
        step = {"id": "snp3", "workflow": "snp-call", "status": "succeeded", "work_dir": "steps/snp3/work"}
        self.state["steps"].append(step)
        self.write_inner(step)
        shared = {"charge_mib": 1024, "memory_mib": 1024, "exclusive": False}
        estimates = {"snp1": {"charge_mib": None, "memory_mib": None, "exclusive": True},
                     "snp2": shared, "snp3": shared}
        (self.outer / "sample-estimates.json").write_text(json.dumps(estimates))

    def test_exclusive_sample_runs_inner_workers_before_small_samples_overlap(self):
        self.add_weighted_third_sample()
        self.write_outer(indices=(1, 2, 3))
        path = self.outer / "worker-1.jsonl"
        events = [json.loads(line) for line in path.read_text().splitlines()]
        for event in events:
            if event.get("task_index") in {2, 3}:
                event["observed_at_unix"] += 7
        path.write_text("".join(json.dumps(event) + "\n" for event in events))
        with self.assertRaisesRegex(ValueError, "exclusive SNP sample"):
            self.check()
        self.write_inner(self.state["steps"][0], workers=2, nested=False)
        evidence = self.check()
        self.assertTrue(evidence["outer_execution"]["simultaneous_child_workers"])
        self.assertTrue(evidence["loaded_r_execution"]["snp1"]["simultaneous_child_workers"])

    def test_unreadable_exclusive_sample_preserves_failure_without_starting_siblings(self):
        self.add_weighted_third_sample()
        self.write_outer(indices=(1,))
        path = self.outer / "worker-1.jsonl"
        path.write_text(path.read_text().replace('"succeeded"', '"failed"'))
        self.state["steps"][0]["status"] = "failed"
        self.check(require_inner=False)

    def test_mismatched_tasks_and_unobserved_batch_cannot_pass(self):
        self.write_outer(indices=(1, 3))
        with self.assertRaisesRegex(ValueError, "every requested sample"):
            self.check()
        self.budget.update(workers=1, reason="workload-not-observed",
                           workload_model="not-observed", memory_per_worker_mib=None)
        self.write_outer()
        with self.assertRaisesRegex(ValueError, "measured"):
            self.check()
        self.check(require_inner=False)
        (self.outer / "job-snp1.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "outer workers"):
            self.check(require_inner=False)

    def test_inconsistent_or_missing_outer_plan(self):
        self.budget["workers"] = 1
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            self.check()
        (self.outer / "worker-1.jsonl").write_text("")
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            self.check()

    def test_requested_serial_has_no_outer_probe_and_no_child_processes(self):
        import shutil
        shutil.rmtree(self.outer)
        self.state.pop("snp_parallel")
        for step in self.state["steps"]:
            self.write_inner(step, serial=True)
        self.assertIsNone(self.check("serial")["outer_admission"])
        self.write_inner(self.state["steps"][0])
        with self.assertRaisesRegex(ValueError, "worker count"):
            self.check("serial")


if __name__ == "__main__":
    unittest.main()
