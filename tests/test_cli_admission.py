"""Two CLI processes must share one runtime even when they write to separate workspaces."""

from contextlib import ExitStack
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from newpat.cli import DockerComposeRunner
from newpat.experiments.transport import DockerTransport
from newpat.paths import ProjectLayout


CPU = 8
MEMORY_MIB = 15858
TIMEOUT = 30


def _run_client(root, name, prepared, admitted, release, repeat):
    # The processes share only their user and Docker runtime, not their runs directory.
    os.environ.update(HOME=str(root), USERPROFILE=str(root), NEWPAT_BACKEND="native")
    workspace = root / name
    layout = ProjectLayout(root / "project", workspace, workspace / "data",
                           workspace / "runs", root / "project" / "compose.yaml")
    runner = DockerComposeRunner(layout, transport=DockerTransport())
    plan = {"steps": [{"id": "dnp", "workflow": "dnp-call"},
                      {"id": "snp_0001", "workflow": "snp-call"}]}
    snapshot = {"runtime": {"effective": {"cpus": CPU, "memory_mib": MEMORY_MIB}}}

    def enter_run(run_name):
        directory = layout.new_run_dir("analysis", run_name)
        return runner.record_run(directory, workflow="analysis", bundled_workflow="workflow-plan-all",
                                 inputs=[], parameters={"plan": plan})

    def prepare():
        runner._image_id = "sha256:" + "a" * 64
        # Both initial runs have reached normal preparation before either requests its budget.
        if runner._record.run_dir.name == "overlap":
            prepared.wait(timeout=TIMEOUT)

    with ExitStack() as stack:
        stack.enter_context(patch.object(runner, "_prepare_runtime", side_effect=prepare))
        stack.enter_context(patch("newpat.resources.ResourceManager.snapshot", return_value=snapshot))
        stack.enter_context(patch("newpat.experiments.runner.DockerComposeRunner._describe_bundled_engine",
                                  return_value={"desktop_scheduling": "step-budget-v1"}))
        with enter_run("overlap"):
            admitted.set()
            if not release.wait(TIMEOUT):
                raise TimeoutError("Test did not release this experiment")
        if repeat is not None:
            if not repeat.wait(TIMEOUT):
                raise TimeoutError("Test did not release the repeated experiment")
            # A wizard may reuse the CLI runner for the next experiment.
            with enter_run("alone"):
                pass


class CliAdmissionTests(unittest.TestCase):
    def run_state(self, directory):
        record = json.loads((directory / "run.json").read_text(encoding="utf-8"))
        compose = json.loads((directory / record["engine_compose"]).read_text(encoding="utf-8"))
        service = compose["services"]["scientific"]
        environment = service["environment"]
        budget = json.loads(environment["NEWPAT_FIXED_RESOURCE_BUDGET"])
        self.assertEqual(budget, record["resource_budget"])
        return record, service, budget

    def test_concurrent_cli_budgets_bound_the_containers_and_release_for_reuse(self):
        ctx = multiprocessing.get_context("spawn")
        prepared = ctx.Barrier(2)
        release, repeat = ctx.Event(), ctx.Event()
        admitted = [ctx.Event(), ctx.Event()]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            clients = [
                ctx.Process(target=_run_client, args=(root, name, prepared, ready, release, again))
                for name, ready, again in zip(("first", "second"), admitted, (repeat, None))
            ]
            try:
                for process in clients:
                    process.start()
                for ready in admitted:
                    self.assertTrue(ready.wait(TIMEOUT), "Both CLI processes must enter before either finishes")
                for name in ("first", "second"):
                    record, service, budget = self.run_state(root / name / "runs" / "overlap")
                    self.assertEqual(record["status"], "running")
                    self.assertEqual(budget["memory_capacity_mib"], MEMORY_MIB // 2)
                    self.assertEqual(budget["cpu_limit"], CPU / 2)
                    self.assertEqual(service["mem_limit"], (MEMORY_MIB // 2) * 2**20)
                    self.assertEqual(float(service["cpus"]), CPU / 2)

                release.set()
                clients[1].join(TIMEOUT)
                self.assertEqual(clients[1].exitcode, 0)
                repeat.set()
                clients[0].join(TIMEOUT)
                self.assertEqual(clients[0].exitcode, 0)
                record, service, budget = self.run_state(root / "first" / "runs" / "alone")
                self.assertEqual(record["status"], "succeeded")
                self.assertEqual((budget["cpu_limit"], budget["memory_capacity_mib"]), (CPU, MEMORY_MIB))
                self.assertNotIn("mem_limit", service)
                self.assertNotIn("cpus", service)
            finally:
                release.set()
                repeat.set()
                for process in clients:
                    if process.is_alive():
                        process.terminate()
                    if process.pid is not None:
                        process.join(TIMEOUT)
