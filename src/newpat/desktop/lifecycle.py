"""Observe abandoned desktop runs without rewriting scientific provenance.

The shared execution lock distinguishes live clients from abandoned runs.
Read-only inspection leaves the recorded status intact when evidence is inconclusive.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import threading
import time

from newpat.errors import RuntimeExecutionError, ValidationError
from newpat.experiments.recovery import reconcile_run
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.tracking import read_run_status
from newpat.resources import ResourceLockBusy, _backend, _resource_lock

_ACTIVE = {"preparing", "running"}
_LIVE_CONTAINERS = {"created", "running", "restarting", "paused"}


class RunObserver:
    def __init__(self, layout, jobs, *, runner_factory=DockerComposeRunner,
                 reconcile=reconcile_run, guard=None):
        self.layout = layout
        self.jobs = jobs
        self.runner_factory = runner_factory
        self.reconcile = reconcile
        self.guard = guard or (lambda: _resource_lock(Path.home(), _backend(), exclusive=True))
        self._cache = {}
        self._pending = set()
        self._lock = threading.RLock()

    def _owned(self, path):
        for job in self.jobs.active()["jobs"]:
            root, run_id = job.get("results_root"), job.get("run_id")
            if root and run_id and (Path(root) / run_id).resolve() == path.resolve():
                return True
        return False

    @staticmethod
    def _result(status, recorded, reason=None, *, can_remove=False):
        return {"status": status, "recorded_status": recorded,
                "status_reason": reason, "can_remove": can_remove}

    def inspect(self, path, metadata):
        """Fresh, bounded check before removal. Never start or stop the engine."""
        recorded = read_run_status(path, metadata)
        if self._owned(path):
            return self._result(recorded, recorded, "active", can_remove=False)
        if recorded not in _ACTIVE:
            # Removing a recorded terminal run hides its card only. An unrelated
            # run may hold the shared execution lock while we update the registry.
            return self._result(recorded, recorded, can_remove=recorded != "unreadable")
        try:
            # Probe only: keeping this exclusive lock during Docker inspection
            # could make an unrelated newly started analysis fail to acquire its
            # shared lock. Run paths are immutable and every re-run has a new ID.
            try:
                with self.guard():
                    pass
                backend_idle = True
            except ResourceLockBusy:
                # The holder might be this run's client, even between containers.
                backend_idle = False
            layout = self.layout()
            # Imported experiments may belong to another computer/backend.
            # The core refuses cross-backend observations, and no source file
            # is altered even when a local interrupted state is confirmed.
            if not path.resolve().is_relative_to(layout.runs_dir.resolve()):
                return self._result("unknown", recorded, "external")
            report = self.reconcile(self.runner_factory(layout), path, stop=False)
            if not report.get("backend_matches") or report.get("error"):
                return self._result("unknown", recorded, "unavailable")
            # A same-name container can belong to a different run or image.
            # The engine can confirm absence without an identity to check.
            present = [item for item in report["containers"] if item.get("state") != "absent"]
            if any(item.get("owned") is True and item.get("state") in _LIVE_CONTAINERS for item in present):
                return self._result("running", recorded, "external_active")
            if (not backend_idle or any(item.get("owned") is not True or item.get("state") not in {"exited", "dead"}
                                        for item in present)):
                return self._result("unknown", recorded, "unavailable")
            # Workflow steps can be complete before the client performs its
            # final input verification/report. Never promote them to success.
            return self._result("interrupted", recorded, "abandoned", can_remove=True)
        except (OSError, ValueError, RuntimeExecutionError, ValidationError):
            return self._result("unknown", recorded, "unavailable")

    def observe(self, path, metadata):
        recorded = read_run_status(path, metadata)
        if self._owned(path):
            return self._result(recorded, recorded, "active")
        if recorded not in _ACTIVE:
            return self._result(recorded, recorded, can_remove=recorded != "unreadable")
        stamp = (path / "run.json").stat()
        # RunRecord is created just before the client takes its execution lock.
        # Do not contend with that short startup window or a fresh status write.
        if time.time() - stamp.st_mtime < 5:
            return self._result("unknown", recorded, "checking")
        key = (str(path.resolve()), stamp.st_mtime_ns, stamp.st_size)
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < 30:
                return deepcopy(cached[1])
            if key not in self._pending and len(self._pending) < 2:
                self._pending.add(key)
                threading.Thread(target=self._observe, args=(key, path, deepcopy(metadata)),
                                 name="newpat-run-observation", daemon=True).start()
        return self._result("unknown", recorded, "checking")

    def _observe(self, key, path, metadata):
        try:
            value = self.inspect(path, metadata)
        except Exception:
            value = self._result("unknown", metadata.get("status"), "unavailable")
        finally:
            with self._lock:
                self._pending.discard(key)
        with self._lock:
            if len(self._cache) >= 128:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic(), value)
