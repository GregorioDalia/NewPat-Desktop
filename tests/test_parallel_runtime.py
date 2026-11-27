"""Exercise the client-to-container execution policy and per-step environment."""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from newpat.errors import RuntimeExecutionError
from newpat.experiments.options import ExecutionOptions
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.transport import DockerTransport
from newpat.paths import ProjectLayout
from newpat_scientific.parallel import THREAD_LIMITS, execution_environment
from test_bundled_runner import engine_metadata


class ParallelRuntimeTests(unittest.TestCase):
    def test_client_passes_policy_into_owned_container_not_host_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            run = root / "runs" / "one"
            (run / "work").mkdir(parents=True)
            layout = ProjectLayout(root, root, root / "data", root / "runs", root / "compose.yaml")
            options = ExecutionOptions(execution_mode="serial", max_workers=3,
                                       dnp_block_mib=16, dnp_block_loci=20,
                                       cpus=2.5, memory_mb=6000)
            runner = DockerComposeRunner(layout, transport=DockerTransport(), options=options)
            runner._record = Mock(run_dir=run, data={})
            with patch.dict(os.environ, {"NIPAT_MAX_WORKERS": "100", "NIPAT_DNP_BLOCK_BYTES": "1"}):
                runner._write_engine_compose("sha256:" + "a" * 64)
                self.assertEqual(os.environ["NIPAT_MAX_WORKERS"], "100")
            service = json.loads((run / "work/engine-compose.json").read_text())["services"]["scientific"]
            environment = service["environment"]
            self.assertEqual(environment["NIPAT_EXECUTION_MODE"], "serial")
            self.assertEqual(environment["NIPAT_MAX_WORKERS"], "3")
            self.assertEqual(environment["NIPAT_DNP_BLOCK_BYTES"], str(16 * 1024**2))
            self.assertEqual(environment["NIPAT_DNP_BLOCK_LOCI"], "20")
            self.assertEqual(environment["NIPAT_CPU_LIMIT"], "2.5")
            self.assertEqual(environment["NIPAT_MEMORY_LIMIT_MIB"], "6000")
            self.assertEqual(service["mem_limit"], 6000 * 1024**2)
            self.assertTrue(all(environment[name] == "1" for name in THREAD_LIMITS))

    def test_dnp_io_and_apple_silicon_worker_policy_follow_the_runtime(self):
        # Identical engine allocations on different physical hosts, explicit
        # per-run limits, and the two independent engine policy switches.
        cases = [
            ("lima", "darwin", "arm64", 8192, 3905, None, True, True),
            ("lima", "darwin", "arm64", 16384, 3905, None, True, True),
            ("lima", "darwin", "arm64", 32768, 8192, 3905, True, True),
            ("lima", "darwin", "arm64", None, 8192, None, True, True),
            ("lima", "darwin", "arm64", 8192, None, None, True, True),
            ("lima", "darwin", "x86_64", 8192, 3905, None, False, False),
            ("native", "linux", "x86_64", 16384, 8192, None, True, False),
            ("native", "linux", "aarch64", 16384, 8192, None, False, False),
            ("native", "darwin", "x86_64", 8192, 3905, None, False, False),
            ("wsl", "win32", "AMD64", 8192, 3905, None, False, False),
            ("wsl", "win32", "arm64", 8192, 3905, None, False, False),
        ]
        for backend, system, arch, host, guest, limit, io, arm_policy in cases:
            with self.subTest(backend=backend, arch=arch, host=host, guest=guest), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                run = root / "runs" / "one"
                (run / "work").mkdir(parents=True)
                layout = ProjectLayout(root, root, root / "data", root / "runs", root / "compose.yaml")
                transport = DockerTransport()
                transport.backend = backend
                runner = DockerComposeRunner(layout, transport=transport, options=ExecutionOptions(memory_mb=limit))
                runner._record = Mock(run_dir=run, data={"resource_snapshot": {
                    "host": {"memory_mib": host, "cpus": 8}, "runtime": {"effective": {"memory_mib": guest, "cpus": 4}},
                }})
                with patch("newpat.experiments.runner.platform.machine", return_value=arch), patch("sys.platform", system):
                    runner._write_engine_compose("sha256:" + "a" * 64)
                compose = json.loads((run / "work/engine-compose.json").read_text())
                env = compose["services"]["scientific"]["environment"]
                if backend == "lima":
                    self.assertEqual(compose["services"]["scientific"]["platform"], "linux/arm64" if arch == "arm64" else "linux/amd64")
                self.assertEqual(env.get("NIPAT_DNP_OPTIMIZED_IO") == "1", io)
                self.assertEqual(env.get("NIPAT_DNP_LIMA_ARM64") == "1", arm_policy)
                self.assertNotIn("NIPAT_MAX_WORKERS", env)
                if limit is not None:
                    self.assertEqual(json.loads(env["NIPAT_FIXED_RESOURCE_BUDGET"])["memory_capacity_mib"], limit)
                if guest is None:
                    self.assertEqual(json.loads(env["NIPAT_FIXED_RESOURCE_BUDGET"])["worker_ceiling"], 1)

    def test_old_runtime_is_rejected_instead_of_silently_ignoring_parallel_settings(self):
        for change in ("capability", "module", "workflow", "serial"):
            with self.subTest(change=change):
                metadata = copy.deepcopy(engine_metadata())
                if change == "capability":
                    del metadata["parallel_execution"]
                elif change == "module":
                    del metadata["preparation"]["file_sha256"]["lib/newpat_scientific/parallel.R"]
                elif change == "workflow":
                    metadata["parallel_execution"]["workflows"].remove("snp-call")
                else:
                    metadata["parallel_execution"]["modes"] = ["auto"]
                with self.assertRaisesRegex(RuntimeExecutionError, "nipat-parallel-v1"):
                    DockerComposeRunner._validate_engine_description(metadata)

    def test_scoped_thread_limits_and_diagnostics_survive_error_without_environment_leak(self):
        inherited = {name: "16" for name in THREAD_LIMITS}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {
            "NIPAT_PARALLEL_LOG_DIR": "old", **inherited,
        }):
            work = Path(temporary) / "work"
            with self.assertRaisesRegex(ValueError, "test"):
                with execution_environment(work) as directory:
                    self.assertTrue(directory.is_dir())
                    self.assertEqual(os.environ["NIPAT_PARALLEL_LOG_DIR"], str(work / "parallel"))
                    self.assertTrue(all(os.environ[name] == "1" for name in THREAD_LIMITS))
                    raise ValueError("test")
            self.assertEqual(os.environ["NIPAT_PARALLEL_LOG_DIR"], "old")
            self.assertTrue(all(os.environ[name] == value for name, value in inherited.items()))

    def test_native_thread_limits_need_no_work_directory_and_preserve_diagnostics(self):
        with patch.dict(os.environ, {"NIPAT_PARALLEL_LOG_DIR": "existing", "VROOM_THREADS": "8"}):
            with execution_environment() as directory:
                self.assertIsNone(directory)
                self.assertEqual(os.environ["NIPAT_PARALLEL_LOG_DIR"], "existing")
                self.assertTrue(all(os.environ[name] == "1" for name in THREAD_LIMITS))
            self.assertEqual(os.environ["VROOM_THREADS"], "8")
            self.assertEqual(os.environ["NIPAT_PARALLEL_LOG_DIR"], "existing")


if __name__ == "__main__":
    unittest.main()
