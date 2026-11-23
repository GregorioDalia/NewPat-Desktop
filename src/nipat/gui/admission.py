"""Coordinate desktop CPU and memory grants across sessions on one runtime."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, replace
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

from nipat.errors import ValidationError
from nipat.preferences import settings_file_lock
from nipat.resources import ResourceLockBusy, fixed_execution_budget, resource_file_lock


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

    def try_admit(self, cpus, memory, options, runtime_idle, *, queued=0):
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
            allocation = None if earlier else _allocate(cpus, memory, options, running, pending + queued)
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

    def boundary_allocation(self, cpus, memory, options, *, commit=False, queued=0):
        """Preview, or reserve after engine acknowledgement, the next step's quota."""
        with settings_file_lock(self.guard):
            mine = json.loads(self.path.read_text(encoding="utf-8"))
            if mine["state"] != "running":
                raise ValidationError("Nessuna quota attiva per questo esperimento.")
            current = Allocation(mine["cpus"], mine["memory_mib"], mine["participants"])
            running, pending = [], 1 + queued  # Include this run's next step.
            for path in self.directory.glob("*.json"):
                if path != self.path:
                    row = json.loads(path.read_text(encoding="utf-8"))
                    if row["state"] == "running":
                        # Includes orphans until Docker confirms they have stopped.
                        running.append(row)
                    else:
                        # A desktop can exit before its pending job reaches Docker.
                        try:
                            with resource_file_lock(path.with_suffix(".owner"), exclusive=True):
                                pass
                        except ResourceLockBusy:
                            pending += 1
                        else:
                            self._remove(path)
            planned = _allocate(cpus, memory, options, running, pending)
            if (planned is None or planned.cpus is None or current.cpus is None
                    or (planned.cpus, planned.memory_mib) == (current.cpus, current.memory_mib)):
                return current if commit else None
            if commit:
                self._write(self.path, {"state": "running", "cpus": planned.cpus,
                                        "memory_mib": planned.memory_mib, "participants": planned.participants})
            return planned


class DesktopStepScheduler:
    """Exchange resource budgets only while the engine is between scientific groups."""

    interface = "step-budget-v1"

    def __init__(self, admission, directory, snapshot, options, *, queued=lambda: 0):
        self.admission = admission
        self.directory = directory
        self.snapshot = snapshot
        self.options = options
        self.queued = queued
        capacity = fixed_execution_budget(snapshot)
        self.cpus = capacity["cpu_limit"]
        self.memory = capacity["memory_capacity_mib"]
        self.token = None
        self._last_signature = None
        self._last_check = 0.0

    def _publish(self, name, message):
        # A bind mount may briefly deny a replacement while the previous
        # message is open on the other side of the Windows or macOS VM.
        for delay in (0.025, 0.05, 0.1, 0.2, 0.4, None):
            try:
                self.admission._write(self.directory / name, message)
                return
            except OSError as exc:
                busy = exc.errno in {errno.EACCES, errno.EPERM, errno.EBUSY} or getattr(exc, "winerror", 0) in {32, 33}
                if delay is None or not busy:
                    raise
                time.sleep(delay)

    def poll(self):
        if self.token is None:
            # Atomic ticket replacements change this directory's timestamp. A
            # periodic full check also covers coarser Windows timestamp updates.
            queued = self.queued()
            signature = (self.admission.directory.stat().st_mtime_ns, queued)
            now = time.monotonic()
            if self._last_signature == signature and now - self._last_check < 2:
                return
            self._last_signature, self._last_check = signature, now
            proposal = self.admission.boundary_allocation(self.cpus, self.memory, self.options, queued=queued)
            if proposal is not None:
                self.token = uuid.uuid4().hex
                self._publish("request.json", {"interface": self.interface, "token": self.token})
            return
        try:
            ack = json.loads((self.directory / "ack.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        if not isinstance(ack, dict) or ack.get("token") != self.token or ack.get("interface") != self.interface:
            return
        # The acknowledgement promises that no scientific children are running.
        # Re-evaluate under the same lock as new entrants before issuing a grant.
        assigned = self.admission.boundary_allocation(self.cpus, self.memory, self.options,
                                                      commit=True, queued=self.queued())
        effective = replace(self.options, cpus=assigned.cpus, memory_mb=assigned.memory_mib)
        budget = fixed_execution_budget(self.snapshot, effective)
        budget["basis"] = "assigned-capacity-at-step-boundary"
        grant = {"interface": self.interface, "token": self.token, "budget": budget}
        with (self.directory / "grants.jsonl").open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(grant, allow_nan=False) + "\n")
        self._publish("grant.json", grant)
        self.token = None

    @contextmanager
    def observing(self, on_error):
        stopped = threading.Event()
        def observe():
            try:
                while not stopped.is_set():
                    self.poll()
                    stopped.wait(0.15)
            except Exception as exc:
                # An unacknowledged engine retains its previous quota. Once it
                # has acknowledged it will fail safely on its bounded timeout.
                on_error(exc)
        watcher = threading.Thread(target=observe, name="newpat-step-budget", daemon=True)
        watcher.start()
        try:
            yield
        finally:
            stopped.set()
            watcher.join()
