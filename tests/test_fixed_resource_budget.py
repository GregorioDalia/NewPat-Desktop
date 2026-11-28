"""Configured resources, not other applications, determine the run ceiling."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from newpat.experiments.options import ExecutionOptions
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.transport import DockerTransport
from newpat.paths import ProjectLayout
from newpat.resources import fixed_execution_budget


def snapshot(memory=8192, cpus=4):
    return {
        "backend": "lima", "host": {"memory_mib": 16384, "cpus": 8},
        "runtime": {"configured": {"memory_mib": memory, "cpus": cpus},
                    "effective": {"memory_mib": memory, "cpus": cpus}},
    }


class FixedResourceBudgetTests(unittest.TestCase):
    def test_capacity_respects_host_runtime_and_container(self):
        state = snapshot()
        policy = fixed_execution_budget(state, ExecutionOptions(cpus=2.5, memory_mb=4096))
        self.assertEqual(policy["memory_capacity_mib"], 4096)
        self.assertEqual(policy["memory_budget_mib"], 3276)
        self.assertEqual(policy["worker_ceiling"], 2)
        self.assertEqual(policy["memory_allocation_per_worker_mib"], 1638)
        self.assertEqual(policy["interface"], "newpat-fixed-resources-v1")
        state["host"]["memory_mib"] = 2048
        self.assertEqual(fixed_execution_budget(state)["memory_capacity_mib"], 2048)

    def test_free_memory_and_current_usage_never_change_the_plan(self):
        state = snapshot()
        expected = fixed_execution_budget(state)
        state["host"].update(memory_available_mib=1, memory_used_mib=16383)
        state["runtime"]["effective"].update(memory_available_mib=1, memory_used_mib=8191)
        self.assertEqual(fixed_execution_budget(state), expected)

    def test_allocations_scale_with_configured_memory_not_absolute_floor(self):
        small = fixed_execution_budget(snapshot(memory=4096))
        large = fixed_execution_budget(snapshot(memory=16384))
        self.assertEqual((small["worker_ceiling"], large["worker_ceiling"]), (4, 4))
        self.assertLess(small["memory_allocation_per_worker_mib"], 2048)
        self.assertGreater(large["memory_allocation_per_worker_mib"], 2048)

    def test_manual_and_serial_modes_bound_the_ceiling(self):
        self.assertEqual(fixed_execution_budget(snapshot(), ExecutionOptions(max_workers=2))["worker_ceiling"], 2)
        self.assertEqual(fixed_execution_budget(snapshot(), ExecutionOptions(execution_mode="serial", max_workers=8))["worker_ceiling"], 1)

    def test_unknown_effective_capacity_keeps_serial_and_is_not_inferred_from_host(self):
        state = snapshot()
        state["runtime"]["effective"] = {}
        policy = fixed_execution_budget(state)
        self.assertEqual(policy["worker_ceiling"], 1)
        self.assertIsNone(policy["memory_capacity_mib"])
        self.assertEqual(policy["reason"], "capacity-unavailable")

    def test_same_assigned_capacity_has_same_plan_on_all_backends(self):
        plans = []
        for backend in ("native", "wsl", "lima"):
            state = snapshot()
            state["backend"] = backend
            plans.append(fixed_execution_budget(state))
        self.assertEqual(plans[0], plans[1])
        self.assertEqual(plans[0], plans[2])

    def test_runner_transmits_the_frozen_policy_instead_of_requerying_resources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "runs" / "one"
            (run / "work").mkdir(parents=True)
            layout = ProjectLayout(root, root, root / "data", root / "runs", root / "compose.yaml")
            runner = DockerComposeRunner(layout, transport=DockerTransport())
            frozen = fixed_execution_budget(snapshot())
            runner._record = Mock(run_dir=run, data={"resource_snapshot": snapshot(), "resource_budget": copy.deepcopy(frozen)})
            runner._record.data["resource_snapshot"]["runtime"]["effective"]["memory_mib"] = 1
            with patch("newpat.resources.ResourceManager.snapshot") as inspect:
                runner._write_engine_compose("sha256:" + "a" * 64)
            inspect.assert_not_called()
            env = json.loads((run / "work/engine-compose.json").read_text())["services"]["scientific"]["environment"]
            self.assertEqual(json.loads(env["NEWPAT_FIXED_RESOURCE_BUDGET"]), frozen)


if __name__ == "__main__":
    unittest.main()
