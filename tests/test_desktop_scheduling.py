from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

from newpat.experiments.options import ExecutionOptions
from newpat.desktop.admission import DesktopAdmission, DesktopStepScheduler
from newpat.resources import fixed_execution_budget
from newpat_scientific.desktop_scheduling import DesktopStepBudget, INTERFACE
from newpat_scientific.errors import PlanExecutionError
from newpat_scientific.executor import _Cancellation, _atomic_json, execute_plan
from newpat_scientific.files import require_file


def budget(cpus=4, memory=4096, **options):
    return fixed_execution_budget({"runtime": {"effective": {"cpus": cpus, "memory_mib": memory}}}, options)


class DesktopStepBudgetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.control = self.root / "desktop-scheduling"
        self.control.mkdir()
        self.initial = budget(max_workers=2)
        self.initial_env = {"NIPAT_DESKTOP_SCHEDULER": str(self.control),
                            "NIPAT_FIXED_RESOURCE_BUDGET": json.dumps(self.initial),
                            "NIPAT_CPU_LIMIT": "3.5", "NIPAT_MEMORY_LIMIT_MIB": "3072", "NIPAT_MAX_WORKERS": "2"}
        self.enterContext(patch.dict(os.environ, self.initial_env))
        self.cancellation = _Cancellation()
        self.scheduler = DesktopStepBudget(self.control, _atomic_json)
        self.first, self.second = "1" * 32, "2" * 32

    def message(self, filename, token, **extra):
        _atomic_json(self.control / filename, {"interface": INTERFACE, "token": token, **extra})

    def request_and_grant(self, token, grant):
        self.message("request.json", token)
        self.message("grant.json", token, budget=grant)

    def test_absent_request_does_no_writes_then_two_grants_apply_with_initial_limits(self):
        self.assertIsNone(self.scheduler.boundary(self.cancellation))
        self.assertFalse(list(self.control.iterdir()))
        self.request_and_grant(self.first, budget(1.5, 1200))
        self.assertEqual(self.scheduler.boundary(self.cancellation),
            {"token": self.first, "cpu_limit": 1.5, "memory_capacity_mib": 1200, "worker_ceiling": 1})
        self.assertEqual(os.environ["NIPAT_CPU_LIMIT"], "1.5")
        self.assertIsNone(self.scheduler.boundary(self.cancellation))
        self.request_and_grant(self.second, budget(8, 8192))
        self.scheduler.boundary(self.cancellation)
        effective = json.loads(os.environ["NIPAT_FIXED_RESOURCE_BUDGET"])
        self.assertEqual((effective["cpu_limit"], effective["memory_capacity_mib"], effective["worker_ceiling"]),
                         (3.5, 3072, 2))
        self.assertEqual(effective["memory_budget_mib"], 2457)
        self.assertEqual(os.environ["NIPAT_MAX_WORKERS"], "2")
        self.scheduler.restore()
        self.assertTrue(all(os.environ[key] == value for key, value in self.initial_env.items()))

    def test_desktop_ledger_and_engine_exchange_a_staggered_lease(self):
        options = ExecutionOptions()
        runtime = {"backend": "native"}
        host = {"runtime": {"effective": {"cpus": 4, "memory_mib": 4096}}}
        first = DesktopAdmission(runtime, "first", home=self.root)
        second = DesktopAdmission(runtime, "second", home=self.root)
        self.enterContext(first.registration())
        def admit(job):
            return job.try_admit(4, 4096, options, lambda _: False)
        self.assertEqual(admit(first).memory_mib, 4096)
        host_scheduler = DesktopStepScheduler(first, self.control, host, options)
        with second.registration():
            self.assertIsNone(admit(second))
            host_scheduler.poll()
            self.assertTrue((self.control / "request.json").exists())
            self.assertIsNone(admit(second))
            def publish(path, document):
                _atomic_json(path, document)
                host_scheduler.poll()
            with patch.object(self.scheduler, "atomic_json", side_effect=publish):
                actual = self.scheduler.boundary(self.cancellation)
            self.assertEqual((actual["cpu_limit"], actual["memory_capacity_mib"]), (2, 2048))
            self.assertEqual((admit(second).cpus, admit(second).memory_mib), (2, 2048))
        self.scheduler.restore()

    def test_temporary_ack_sharing_failure_retries_the_same_token(self):
        self.request_and_grant(self.first, budget(2, 2000))
        messages = []
        def publish(path, document):
            messages.append(document.copy())
            if len(messages) == 1:
                raise PermissionError(errno.EACCES, "remote read handle")
            _atomic_json(path, document)
        with patch.object(self.scheduler, "atomic_json", side_effect=publish):
            result = self.scheduler.boundary(self.cancellation)
        self.assertEqual(result["token"], self.first)
        self.assertEqual(messages, [{"interface": INTERFACE, "token": self.first}] * 2)
        self.scheduler.restore()

    def test_matching_grant_is_required_before_any_new_work(self):
        self.message("request.json", self.first)
        self.message("grant.json", self.second, budget=budget(1, 256))
        with patch("newpat_scientific.desktop_scheduling._GRANT_TIMEOUT", 0), self.assertRaisesRegex(PlanExecutionError, "Timed out"):
            self.scheduler.boundary(self.cancellation)
        self.assertEqual(json.loads((self.control / "ack.json").read_text())["token"], self.first)
        self.assertEqual(os.environ["NIPAT_FIXED_RESOURCE_BUDGET"], self.initial_env["NIPAT_FIXED_RESOURCE_BUDGET"])
        for invalid in ({"memory_capacity_mib": 0}, {"cpu_limit": False}, {"worker_ceiling": 1.5},
                        {"memory_reserve_fraction": 1}, {"interface": "unknown"}):
            with self.subTest(invalid=invalid):
                self.message("grant.json", self.first, budget={**budget(), **invalid})
                with self.assertRaisesRegex(PlanExecutionError, "Invalid"):
                    self.scheduler.boundary(self.cancellation)

    def snp_plan(self):
        # Model the container's input mount while running preflight on the host.
        def mounted_file(path, label):
            if path.parent == Path("/inputs"):
                path = self.root / path.name
            return require_file(path, label)

        self.enterContext(patch("newpat_scientific.executor.require_file", new=mounted_file))
        panel = self.root / "panel.tsv"
        panel.write_text("chr\tpos\tref\talt\nchr1\t10\tA\tG\n")
        plan = {"schema_version": 1, "samples": [], "steps": []}
        for name in ("s1", "s2"):
            source = self.root / (name + ".pileup")
            source.write_text("chr1\t10\tA\t2\t.G\tII\tread1,read2\n")
            plan["samples"].append({"id": name, "kind": "snp-pileup", "path": f"/inputs/{source.name}"})
            plan["steps"].append({"id": "call_" + name, "workflow": "snp-call",
                "inputs": {"sample": name, "panel": "/inputs/panel.tsv", "reference": None}, "parameters": {"mode": "pileup"}})
        script = self.root / "SNPcall.R"
        script.touch()
        return plan, {"snp-call": script}

    def test_no_handoff_within_snp_batch_and_new_budget_before_summary(self):
        plan, scripts = self.snp_plan()
        self.request_and_grant(self.first, budget(2, 2000))
        def batch(plan, state, *args, **kwargs):
            self.assertEqual(os.environ["NIPAT_MEMORY_LIMIT_MIB"], "2000")
            self.request_and_grant(self.second, budget(1, 1000))
            for step in state["steps"]:
                step.update(status="succeeded", artifacts={"snp-tables": []})
            self.assertEqual(json.loads((self.control / "ack.json").read_text())["token"], self.first)
            return True
        def summary(*args, before_group):
            before_group()
            self.assertEqual(os.environ["NIPAT_MEMORY_LIMIT_MIB"], "1000")
            return []
        with patch("newpat_scientific.snp_parallel.execute_independent_snp_steps", side_effect=batch), \
                patch("newpat_scientific.snp_summary.finalize_snp_summaries", side_effect=summary):
            state = execute_plan(plan, run_dir=self.root / "workflow", script_paths=scripts)
        self.assertEqual(state["status"], "succeeded", state)
        self.assertEqual([grant["next_phase"] for grant in state["desktop_resource_grants"]], ["snp-batch", "snp-summary"])
        self.assertTrue(all(os.environ[key] == value for key, value in self.initial_env.items()))

    def test_one_sample_has_no_summary_calculation_to_renegotiate(self):
        plan, scripts = self.snp_plan()
        plan["samples"] = plan["samples"][:1]
        plan["steps"] = plan["steps"][:1]
        def final_step(plan, step, record, *args):
            self.message("request.json", self.first)
            record.update(status="succeeded", artifacts={"snp-tables": []})
        with patch("newpat_scientific.executor._execute_step", side_effect=final_step):
            state = execute_plan(plan, run_dir=self.root / "workflow", script_paths=scripts)
        self.assertEqual(state["status"], "succeeded", state)
        self.assertFalse((self.control / "ack.json").exists())
        self.assertNotIn("desktop_resource_grants", state)

    def test_cancel_after_ack_blocks_unstarted_steps(self):
        plan, scripts = self.snp_plan()
        self.message("request.json", self.first)
        def cancel_after_ack(path, document):
            _atomic_json(path, document)
            if path.name == "ack.json":
                signal.raise_signal(signal.SIGTERM)
        with patch("newpat_scientific.executor._atomic_json", side_effect=cancel_after_ack):
            state = execute_plan(plan, run_dir=self.root / "workflow", script_paths=scripts)
        self.assertEqual((state["status"], state["exit_code"]), ("cancelled", 143), state)
        self.assertEqual([step["status"] for step in state["steps"]], ["blocked", "blocked"])


if __name__ == "__main__":
    unittest.main()
