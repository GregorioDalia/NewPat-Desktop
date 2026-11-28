"""Coordinate CPU and memory grants across NewPat clients on one runtime."""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, replace
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

from newpat.errors import RuntimeExecutionError, ValidationError
from newpat.experiments.runner import DockerComposeRunner, PLAN_WORKFLOWS
from newpat.preferences import settings_file_lock
from newpat.processes import background_process_options
from newpat.resources import ResourceLockBusy, fixed_execution_budget, resource_file_lock


@dataclass(frozen=True)
class Allocation:
    cpus: float | None
    memory_mib: int | None
    participants: int


def _share(available, lanes, pending, limits):
    # When all waiting jobs fit, reserve only what a capped peer can use.
    # Unknown (including older) peers retain their proportional share.
    if lanes == pending:
        for limit in sorted(limits):
            if lanes == 1 or limit >= available // lanes:
                break
            available -= limit
            lanes -= 1
    return available // lanes


def _allocate(cpus, memory, requested, running, pending, waiting=()):
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
    cpu_caps = (round(row["requested_cpus"] * 10**9) for row in waiting if row.get("requested_cpus") is not None)
    mem_caps = (row["requested_memory_mib"] for row in waiting if row.get("requested_memory_mib") is not None)
    cpu_quota = min(requested_cpu, _share(free_cpu, lanes, pending, cpu_caps)) / 10**9
    memory_quota = min(requested.memory_mb or memory, _share(free_mem, lanes, pending, mem_caps))
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
        self.directory = (home or Path.home()) / ".newpat" / "desktop-scheduling" / identity
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

    @staticmethod
    def _has_owner(path):
        try:
            with resource_file_lock(path.with_suffix(".owner"), exclusive=True):
                return False
        except ResourceLockBusy:
            return True

    def _check_orphans(self, paths, now, runtime_idle, *, computing=False):
        # Probe outside the registry lock; require two spaced idle observations
        # so a crashed caller's in-flight Docker create can become visible.
        if computing and paths:
            # Shutdown joins the observer. Limit each pass to one runtime probe
            # and rotate stale tickets even if the oldest container stays alive.
            paths = (min(paths, key=lambda p: self._orphan_checks.get(p, (-math.inf, False))[0]),)
        for path in paths:
            checked, previously_idle = self._orphan_checks.get(path, (None, False))
            if checked is not None and now - checked < 2:
                continue
            try:
                idle = runtime_idle(path.stem)
            except (OSError, RuntimeExecutionError):
                self._orphan_checks[path] = (now, False)
                if computing:
                    continue  # Keep the orphan's charge and the current calculation's budget.
                raise
            self._orphan_checks[path] = (now, idle)
            if previously_idle and idle:
                with settings_file_lock(self.guard):
                    self._remove(path)

    def try_admit(self, cpus, memory, options, runtime_idle, *, queued=0):
        orphans = []
        with settings_file_lock(self.guard):
            running, waiting, earlier = [], [], False
            mine = json.loads(self.path.read_text(encoding="utf-8"))
            if mine["state"] == "running":
                return Allocation(mine["cpus"], mine["memory_mib"], mine["participants"])
            if mine["state"] == "preparing":
                mine = {"state": "ready", "since": time.monotonic_ns(),
                        "requested_cpus": options.cpus, "requested_memory_mib": options.memory_mb}
                self._write(self.path, mine)
            for path in self.directory.glob("*.json"):
                if path == self.path:
                    continue
                row = json.loads(path.read_text(encoding="utf-8"))
                if not self._has_owner(path):
                    if row["state"] != "running":
                        self._remove(path)
                        continue
                    orphans.append(path)
                if row["state"] == "running":
                    running.append(row)
                else:
                    waiting.append(row)
                    if row["state"] == "ready" and (row["since"], path) < (mine["since"], self.path):
                        earlier = True
            pending = 1 + len(waiting) + queued
            allocation = None if earlier else _allocate(cpus, memory, options, running, pending, waiting)
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
        self._check_orphans(orphans, now, runtime_idle)
        return None

    def boundary_allocation(self, cpus, memory, options, *, commit=False, queued=0, runtime_idle=None):
        """Preview, or reserve after engine acknowledgement, the next step's quota."""
        orphans = []
        with settings_file_lock(self.guard):
            mine = json.loads(self.path.read_text(encoding="utf-8"))
            if mine["state"] != "running":
                raise ValidationError("Nessuna quota attiva per questo esperimento.")
            current = Allocation(mine["cpus"], mine["memory_mib"], mine["participants"])
            running, waiting = [], []
            for path in self.directory.glob("*.json"):
                if path != self.path:
                    row = json.loads(path.read_text(encoding="utf-8"))
                    if row["state"] == "running":
                        running.append(row)
                        if runtime_idle is not None and not self._has_owner(path):
                            orphans.append(path)
                    elif self._has_owner(path):
                        waiting.append(row)
                    else:
                        self._remove(path)
            planned = _allocate(cpus, memory, options, running, 1 + len(waiting) + queued, waiting)
            if (planned is None or planned.cpus is None or current.cpus is None
                    or (planned.cpus, planned.memory_mib) == (current.cpus, current.memory_mib)):
                planned = current if commit else None
            elif commit:
                self._write(self.path, {"state": "running", "cpus": planned.cpus,
                                        "memory_mib": planned.memory_mib, "participants": planned.participants})
        if orphans:
            self._check_orphans(orphans, time.monotonic(), runtime_idle, computing=True)
        return planned


class DesktopStepScheduler:
    """Exchange resource budgets only while the engine is between scientific groups."""

    interface = "step-budget-v1"

    def __init__(self, admission, directory, snapshot, options, *, queued=lambda: 0, runtime_idle=None):
        self.admission = admission
        self.directory = directory
        self.snapshot = snapshot
        self.options = options
        self.queued = queued
        self.runtime_idle = runtime_idle
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
            proposal = self.admission.boundary_allocation(self.cpus, self.memory, self.options, queued=queued,
                                                        runtime_idle=self.runtime_idle)
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


class CoordinatedComposeRunner(DockerComposeRunner):
    """Register CLI and GUI experiments in the same per-runtime admission queue."""

    def __init__(self, *args, queued_siblings=lambda: 0, after_admission=lambda: None,
                 language="it", **kwargs):
        super().__init__(*args, **kwargs)
        self._admission = None
        self._step_scheduler = None
        self._queued_siblings = queued_siblings
        self._after_admission = after_admission
        self._scheduling_language = language

    def _project_idle(self, job_id):
        # Docker Compose labels scientific containers with our unique project.
        # Exited containers no longer consume the running quota.
        command = ["docker", "ps", "--all", "--quiet", "--filter",
                   "label=com.docker.compose.project=newpat-" + job_id]
        for status in ("created", "running", "restarting", "paused", "removing"):
            command.extend(["--filter", "status=" + status])
        environment = self._environment()
        try:
            result = subprocess.run(self._transport.command(command, environment), env=environment,
                                    stdin=subprocess.DEVNULL, capture_output=True, check=True,
                                    timeout=8, **background_process_options())
        except (OSError, subprocess.SubprocessError) as exc:
            message = ("Cannot confirm that the previous experiment has stopped. Check the runtime and retry."
                       if self._scheduling_language == "en" else
                       "Impossibile verificare l’arresto dell’esperimento precedente. Controlla il runtime e riprova.")
            raise RuntimeExecutionError(message) from exc
        return not result.stdout.strip()

    def _base_command(self):
        command = super()._base_command()
        if self._admission is not None:
            command.extend(["--project-name", "newpat-" + self._admission.id])
        return command

    @contextmanager
    def record_run(self, *args, **kwargs):
        if self._record is not None:
            raise RuntimeExecutionError("Questo runner sta già registrando un’esecuzione.")
        requested = self.options
        previous = self._admission
        if previous is None and not self.dry_run:
            self._admission = DesktopAdmission(self._transport.metadata, uuid.uuid4().hex)
        try:
            registration = nullcontext() if self.dry_run else self._admission.registration()
            with registration, super().record_run(*args, **kwargs) as record:
                yield record
        finally:
            # A wizard can reuse this runner for several experiments. A prior
            # allocation must not become a user limit or an orphan's identity.
            self.options = requested
            self._step_scheduler = None
            self._admission = previous

    def _wait_for_admission(self, first_wait):
        if first_wait:
            self._write("In attesa delle risorse condivise con gli altri esperimenti.\n")
        time.sleep(0.3)

    def _describe_bundled_engine(self):
        self._step_scheduler = None
        result = super()._describe_bundled_engine()
        if (self._bundled_workflow in PLAN_WORKFLOWS and self._record is not None
                and result.get("desktop_scheduling") == DesktopStepScheduler.interface):
            data = self._record.data
            assigned = data["concurrent_execution"]
            if assigned["assigned_cpus"] is not None and assigned["assigned_memory_mib"] is not None:
                directory = self._record.run_dir / "work" / "desktop-scheduling"
                directory.mkdir()
                self._step_scheduler = DesktopStepScheduler(
                    self._admission, directory, data["resource_snapshot"], self.options,
                    queued=self._queued_siblings, runtime_idle=self._project_idle,
                )
                assigned["step_scheduling"] = {"interface": DesktopStepScheduler.interface,
                                               "grants": "work/desktop-scheduling/grants.jsonl"}
        return result

    def _record_resource_snapshot(self):
        super()._record_resource_snapshot()
        if self.dry_run or self._record is None:
            return

        data = self._record.data
        snapshot = data["resource_snapshot"]
        capacity = fixed_execution_budget(snapshot)
        cpu, memory = capacity["cpu_limit"], capacity["memory_capacity_mib"]
        requested = self.options
        waiting = False
        while True:
            allocation = self._admission.try_admit(cpu, memory, requested, self._project_idle,
                                                   queued=self._queued_siblings())
            if allocation is not None:
                break
            self._wait_for_admission(not waiting)
            waiting = True
        self._after_admission()
        if allocation.participants > 1:
            self.options = replace(requested, cpus=allocation.cpus, memory_mb=allocation.memory_mib)
        data["concurrent_execution"] = {"participants_at_admission": allocation.participants,
                                        "requested_options": requested.as_dict(),
                                        "assigned_cpus": allocation.cpus,
                                        "assigned_memory_mib": allocation.memory_mib,
                                        "waited": waiting}
        data["execution_options"] = self.options.as_dict()
        snapshot["container"] = {"memory_mib": self.options.memory_mb, "cpus": self.options.cpus}
        data["resource_budget"] = fixed_execution_budget(snapshot, self.options)
        if allocation.participants > 1:
            message = ("Assigned to this experiment" if self._scheduling_language == "en"
                       else "Risorse assegnate a questo esperimento")
            self._write(f"{message}: {allocation.cpus:g} CPU, {allocation.memory_mib} MiB.\n")
        self._record.save()

    def run(self, *args, **kwargs):
        observer = nullcontext()
        if self._step_scheduler is not None:
            def report_error(exc):
                prefix = ("Desktop step scheduling interrupted" if self._scheduling_language == "en"
                          else "Coordinamento delle risorse tra i passi interrotto")
                self._write(f"{prefix}: {exc}\n")
            observer = self._step_scheduler.observing(report_error)
        try:
            with observer:
                return super().run(*args, **kwargs)
        finally:
            if self._admission is not None and self._record is not None and self._record.data.get("commands"):
                stage = self._record.data["commands"][-1]
                cleanup = stage.get("container_cleanup", {}).get("status")
                if stage.get("started_at") and cleanup not in {"removed", "stopped", "absent"}:
                    self._admission.unconfirmed_cleanup = True
