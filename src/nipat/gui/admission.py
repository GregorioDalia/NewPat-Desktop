"""Coordinate fixed scientific-container quotas across desktop sessions on one runtime."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import time

from nipat.errors import ValidationError
from nipat.preferences import settings_file_lock
from nipat.resources import ResourceLockBusy, resource_file_lock


@dataclass(frozen=True)
class Allocation:
    cpus: float | None
    memory_mib: int | None
    participants: int


def _allocate(cpus, memory, requested, running, pending):
    """Divide the uncommitted capacity only. CPU quotas use Docker's nanocpu unit."""
    participants = len(running) + pending
    if cpus is None or memory is None or memory < 128 or any(
        row["cpus"] is None or row["memory_mib"] is None for row in running
    ):
        if running:
            return None
        # Unknown capacity or less than the minimum configurable container
        # limit admits one calculation with its original settings.
        return Allocation(None, None, 1)
    total_cpu = round(cpus * 10**9)
    requested_cpu = round((requested.cpus or cpus) * 10**9)
    if total_cpu < 1 or requested_cpu < 1:
        raise ValidationError("Il limite CPU è inferiore alla precisione supportata dal runtime.")
    free_cpu = total_cpu - sum(round(row["cpus"] * 10**9) for row in running)
    free_mem = memory - sum(row["memory_mib"] for row in running)
    # An automatic concurrent job normally gets at least one CPU and its
    # proportional share of guest RAM. Explicit smaller ceilings are honored.
    cpu_floor = min(total_cpu, 10**9, requested_cpu)
    mem_per_cpu = max(128, math.floor(memory / max(1, math.floor(cpus))))
    mem_floor = min(memory, requested.memory_mb or memory, mem_per_cpu)
    if free_cpu < max(1, cpu_floor) or free_mem < mem_floor:
        return None
    lanes = max(1, min(pending, free_cpu // 10**9, free_mem // mem_per_cpu))
    cpu_quota = min(requested_cpu, free_cpu // lanes) / 10**9
    memory_quota = min(requested.memory_mb or memory, free_mem // lanes)
    return Allocation(cpu_quota, memory_quota, participants)


class DesktopAdmission:
    def __init__(self, runtime, job_id, *, home=None):
        backend = runtime["backend"]
        if backend == "wsl":
            target = [backend, runtime["wsl_distro"].casefold()]
        elif backend == "lima":
            target = [backend, str(Path(runtime["lima_home"]).resolve()), runtime["lima_instance"]]
        else:
            target = [backend, os.environ.get("DOCKER_CONTEXT"), os.environ.get("DOCKER_HOST")]
        identity = hashlib.sha256(json.dumps(target).encode()).hexdigest()[:24]
        self.directory = (home or Path.home()) / ".nipat" / "desktop-scheduling" / identity
        self.id = job_id
        self.path = self.directory / (job_id + ".json")
        self.guard = self.directory / "admission"
        self.unconfirmed_cleanup = False
        self._orphan_checks = {}

    @staticmethod
    def _write(path, row):
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(row, allow_nan=False), encoding="utf-8")
        temporary.replace(path)

    def _remove(self, path):
        path.unlink(missing_ok=True)
        path.with_suffix(".owner").unlink(missing_ok=True)
        path.with_suffix(".tmp").unlink(missing_ok=True)

    @contextmanager
    def registration(self):
        """Register before input hashing. OS releases the owner lock on a crash."""
        owner = self.path.with_suffix(".owner")
        self.directory.mkdir(parents=True, exist_ok=True)
        try:
            with resource_file_lock(owner, exclusive=True):
                with settings_file_lock(self.guard):
                    if self.path.exists():
                        raise ValidationError("Identificativo di esperimento già registrato.")
                    self._write(self.path, {"state": "preparing"})
                try:
                    yield
                finally:
                    with settings_file_lock(self.guard):
                        if not self.unconfirmed_cleanup:
                            self.path.unlink(missing_ok=True)
        finally:
            # Owner filenames are unique. Without a registration no other
            # client will ever open this file again.
            if not self.path.exists():
                owner.unlink(missing_ok=True)

    def try_admit(self, cpus, memory, options, runtime_idle):
        orphans = []
        with settings_file_lock(self.guard):
            running, pending, earlier = [], 0, False
            mine = json.loads(self.path.read_text(encoding="utf-8"))
            if mine["state"] == "running":
                return Allocation(mine["cpus"], mine["memory_mib"], mine["participants"])
            if mine["state"] == "preparing":
                mine = {"state": "ready", "since": time.monotonic_ns()}
                self._write(self.path, mine)
            for path in self.directory.glob("*.json"):
                row = mine if path == self.path else json.loads(path.read_text(encoding="utf-8"))
                if path != self.path:
                    try:
                        with resource_file_lock(path.with_suffix(".owner"), exclusive=True):
                            pass
                    except ResourceLockBusy:
                        pass
                    else:
                        if row["state"] != "running":
                            self._remove(path)
                            continue
                        # A crashed desktop can leave a live Docker container.
                        orphans.append(path)
                if row["state"] == "running":
                    running.append(row)
                else:
                    pending += 1
                    if row["state"] == "ready" and (row["since"], path) < (mine["since"], self.path):
                        earlier = True
            allocation = None if earlier else _allocate(cpus, memory, options, running, pending)
            now = time.monotonic() if orphans else 0
            # Reconcile even a partial stale reservation: otherwise solitary
            # future jobs could each inherit the same permanently reduced quota.
            pending_probe = any(path not in self._orphan_checks
                                or self._orphan_checks[path][1]
                                or now - self._orphan_checks[path][0] >= 2 for path in orphans)
            if allocation is not None and not pending_probe:
                self._write(self.path, {"state": "running", "cpus": allocation.cpus,
                                        "memory_mib": allocation.memory_mib,
                                        "participants": allocation.participants})
                return allocation
        # Never hold the registry lock during a runtime call. Require two
        # observations, separated in time, to allow an in-flight Docker create.
        for path in orphans:
            checked, previously_idle = self._orphan_checks.get(path, (None, False))
            if checked is not None and now - checked < 2:
                continue
            idle = runtime_idle(path.stem)
            self._orphan_checks[path] = (now, idle)
            if previously_idle and idle:
                with settings_file_lock(self.guard):
                    self._remove(path)
        return None
