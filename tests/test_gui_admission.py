"""Exercise default desktop admissions under bursts, staggered starts and cancellation."""

from collections import deque
from contextlib import ExitStack
from functools import partial
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from nipat.execution.options import ExecutionOptions
from nipat.gui.admission import DesktopAdmission
from nipat.gui.jobs import JobManager


class DesktopAdmissionTests(unittest.TestCase):
    cpus = 4
    memory = 3905

    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.home = Path(temporary)
        self.options = ExecutionOptions()

    def register(self, stack, index):
        job = DesktopAdmission({"backend": "native"}, f"job-{index:03d}", home=self.home)
        lease = stack.enter_context(ExitStack())
        lease.enter_context(job.registration())
        return job, lease

    def admit(self, job, *, queued=0):
        def unexpected_orphan_check(job_id):
            self.fail(f"Live registrations should never require a runtime lookup: {job_id}")
        return job.try_admit(self.cpus, self.memory, self.options, unexpected_orphan_check, queued=queued)

    def check_limits(self, active):
        allocations = [self.admit(job) for job in active]
        self.assertTrue(all(a is not None for a in allocations))
        for a in allocations:
            self.assertGreater(a.cpus, 0)
            self.assertGreaterEqual(a.memory_mib, 128)
        self.assertLessEqual(sum(round(a.cpus * 10**9) for a in allocations), self.cpus * 10**9)
        self.assertLessEqual(sum(a.memory_mib for a in allocations), self.memory)

    def test_default_bursts_serve_all_survivors_within_aggregate_capacity(self):
        for count in (3, 5, 13):
            with self.subTest(count=count), ExitStack() as stack:
                registrations = [self.register(stack, n) for n in range(count)]
                active, waiting, admitted = [], [], []
                for i, (job, _) in enumerate(registrations):
                    if self.admit(job) is None:
                        waiting.append(i)
                    else:
                        active.append(i)
                        admitted.append(i)
                    self.check_limits([registrations[j][0] for j in active])
                self.assertEqual(len(active), min(self.cpus, count))
                cancelled = set()
                if waiting:
                    i = waiting.pop(0)
                    registrations[i][1].close()
                    cancelled.add(i)
                while waiting:
                    finished = active.pop(0)
                    registrations[finished][1].close()
                    i = waiting.pop(0)
                    self.assertIsNotNone(self.admit(registrations[i][0]))
                    active.append(i)
                    admitted.append(i)
                    self.check_limits([registrations[j][0] for j in active])
                self.assertEqual(admitted, [i for i in range(count) if i not in cancelled])

    def test_first_quota_counts_requests_waiting_to_prepare(self):
        for count in (3, 5, 13):
            with self.subTest(count=count), ExitStack() as stack:
                first, _ = self.register(stack, 0)
                self.register(stack, 1)
                # Only two preparers have files in the registry. The other GUI
                # requests still count when sizing the first scientific process.
                quota = self.admit(first, queued=count - 2)
                lanes = min(self.cpus, count)
                self.assertEqual(quota.participants, count)
                self.assertEqual(round(quota.cpus * 10**9), self.cpus * 10**9 // lanes)
                self.assertEqual(quota.memory_mib, self.memory // lanes)

    def test_staggered_default_arrivals_give_up_quota_at_step_boundaries(self):
        for count in (3, 5, 13):
            with self.subTest(count=count), ExitStack() as stack:
                registrations = [self.register(stack, 0)]
                first = registrations[0][0]
                full = self.admit(first)
                self.assertEqual((full.cpus, full.memory_mib), (self.cpus, self.memory))

                # The first calculation has started when later experiments arrive.
                for i in range(1, count):
                    job, lease = self.register(stack, i)
                    registrations.append((job, lease))
                    self.assertIsNone(self.admit(job))
                registrations[1][1].close()
                self.assertEqual(self.admit(first), full)

                # Until the engine confirms the change, no waiter may use the offer.
                offered = first.boundary_allocation(self.cpus, self.memory, self.options, commit=False)
                self.assertIsNotNone(offered)
                for job, _ in registrations[2:]:
                    self.assertIsNone(self.admit(job))
                self.assertEqual(self.admit(first), full)
                first.boundary_allocation(self.cpus, self.memory, self.options, commit=True)

                active, waiting, admitted = [0], [], [0]
                for i, (job, _) in enumerate(registrations[2:], start=2):
                    if self.admit(job) is None:
                        waiting.append(i)
                    else:
                        active.append(i)
                        admitted.append(i)
                    self.check_limits([registrations[j][0] for j in active])
                self.assertGreater(len(active), 1)
                # Let survivors advance without another engine boundary.
                while waiting:
                    registrations[active.pop(0)][1].close()
                    i = waiting.pop(0)
                    self.assertIsNotNone(self.admit(registrations[i][0]))
                    active.append(i)
                    admitted.append(i)
                    self.check_limits([registrations[j][0] for j in active])
                self.assertEqual(admitted, [0, *range(2, count)])

    def prepared(self):
        return SimpleNamespace(
            assert_inputs_unchanged=Mock(), inputs={}, scientific_settings={},
            layout=SimpleNamespace(runs_dir=self.home),
            draft={"name": "test", "caller": "dnp", "samples": []},
        )

    def complete_run(self, run_name):
        path = Path(tempfile.mkdtemp(prefix=run_name + "-", dir=self.home))
        (path / "run.json").write_text('{"schema_version":1,"status":"succeeded"}', encoding="utf-8")
        return path

    def test_job_manager_keeps_more_than_one_hundred_unfinished_requests(self):
        # Start the real JobManager worker callbacks under explicit test control.
        # Queueing their entry points avoids allocating a hundred OS threads.
        callbacks = deque()
        started = []
        backlog = []

        def deferred_thread(*, target, args, **_):
            return SimpleNamespace(start=lambda: callbacks.append(partial(target, *args)))

        def runner(_prepared, job):
            started.append(job.id)
            backlog.append(job.queued_siblings())
            return SimpleNamespace(last_run_dir=None, job=job)

        def workflows(_layout, runner, _settings):
            def analyze(*, run_name, **_):
                runner.job.admission_ready()
                return self.complete_run(run_name)
            return SimpleNamespace(analyze=analyze)

        prepared = self.prepared()
        manager = JobManager(runner_factory=runner, workflows_factory=workflows)
        with patch("nipat.gui.jobs.threading.Thread", new=deferred_thread):
            ids = [manager.start(prepared)["id"] for _ in range(103)]
            self.assertEqual({j["id"] for j in manager.active()["jobs"]}, set(ids))
            self.assertEqual(len(callbacks), 2)
            self.assertEqual(manager.get(ids[-1])["status"], "queued")
            self.assertEqual(manager.cancel(ids[-1])["status"], "interrupted")
            self.assertEqual(manager.wait(ids[-1], 0)["status"], "interrupted")
            self.assertEqual(len(callbacks), 2)
            latest = manager.start(prepared)["id"]
            expected = ids[:-1] + [latest]
            self.assertEqual({j["id"] for j in manager.active()["jobs"]}, set(expected))
            self.assertEqual({j["id"] for j in manager.list()}, set(expected))
            while callbacks:
                self.assertLessEqual(len(callbacks), 2)
                callbacks.popleft()()
            self.assertEqual(started, expected)
            self.assertEqual((backlog[0], backlog[-1]), (101, 0))
            self.assertFalse(manager.active()["active"])
            self.assertTrue(all(manager.get(i)["status"] == "succeeded" for i in expected))

    def test_preparation_limit_does_not_limit_scientific_calculations(self):
        release_preparation, release_science = threading.Event(), threading.Event()
        first_pair, all_computing = threading.Event(), threading.Event()
        lock = threading.Lock()
        preparing, computing = set(), set()
        peak_preparing = 0
        count = 5

        def workflows(_layout, runner, _settings):
            def analyze(*, run_name, **_):
                nonlocal peak_preparing
                job = runner.job
                with lock:
                    preparing.add(job.id)
                    peak_preparing = max(peak_preparing, len(preparing))
                    if len(preparing) == 2:
                        first_pair.set()
                if not release_preparation.wait(10):
                    raise TimeoutError("Timed out releasing preparation")
                with lock:
                    preparing.remove(job.id)
                job.admission_ready()
                with lock:
                    computing.add(job.id)
                    if len(computing) == count:
                        all_computing.set()
                if not release_science.wait(10):
                    raise TimeoutError("Timed out releasing computation")
                return self.complete_run(run_name)
            return SimpleNamespace(analyze=analyze)

        manager = JobManager(runner_factory=lambda _, job: SimpleNamespace(job=job, last_run_dir=None),
                             workflows_factory=workflows)
        ids = []
        try:
            for _ in range(count):
                ids.append(manager.start(self.prepared())["id"])
            self.assertTrue(first_pair.wait(5))
            self.assertEqual([manager.get(i)["status"] for i in ids[2:]], ["queued"] * 3)
            release_preparation.set()
            self.assertTrue(all_computing.wait(5))
            self.assertEqual(peak_preparing, 2)
            self.assertEqual(computing, set(ids))
        finally:
            release_preparation.set()
            release_science.set()
            results = [manager.wait(i, 5) for i in ids]
        self.assertEqual([r["status"] for r in results], ["succeeded"] * count)
