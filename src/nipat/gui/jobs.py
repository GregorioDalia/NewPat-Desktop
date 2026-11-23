"""Asynchronous desktop jobs around the existing runner, with owned cancellation."""
from __future__ import annotations

from collections import OrderedDict, deque
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from itertools import islice
from pathlib import Path
import subprocess
import threading
import time
import uuid

from nipat.errors import RuntimeExecutionError, ValidationError
from nipat.execution.progress import ProgressSnapshot
from nipat.execution.recovery import reconcile_run
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.tracking import read_run_status
from nipat.execution.workflows import Workflows
from nipat.gui.admission import DesktopAdmission, DesktopStepScheduler
from nipat.gui.plan import PreparedAnalysis
from nipat.processes import background_process_options

_TERMINAL = {"succeeded", "failed", "interrupted", "planned"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Job:
    def __init__(self, prepared: PreparedAnalysis, manager: JobManager | None = None):
        self.id = uuid.uuid4().hex
        self.prepared = prepared
        self.name = prepared.draft["name"]
        self.status = "starting"
        self.created_at = _now()
        self.started_monotonic = time.monotonic()
        self.finished_at = None
        self.run_dir: Path | None = None
        self.progress = None
        self.error = None
        self.logs = deque(maxlen=250)
        self.log_revision = 0
        self.events = deque(maxlen=5)
        self.event_revision = 0
        self.sample_labels = tuple(dict.fromkeys(sample["id"] for sample in prepared.draft["samples"]))
        self.cancel_event = threading.Event()
        self.done = threading.Event()
        self.lock = threading.RLock()
        self.runner = None
        self.thread = None
        self._manager = manager

    def admission_ready(self) -> None:
        if self._manager is not None:
            self._manager.preparation_finished(self.id)

    def queued_siblings(self) -> int:
        return self._manager.waiting_to_prepare() if self._manager is not None else 0

    def snapshot(self, *, include_logs=True) -> dict:
        with self.lock:
            status = "finalizing" if self.status in _TERMINAL and not self.done.is_set() else self.status
            return {"id": self.id, "name": self.name, "status": status,
                    "created_at": self.created_at, "finished_at": self.finished_at,
                    "run_id": self.run_dir.name if self.run_dir else None,
                    "results_root": str(self.prepared.layout.runs_dir),
                    "progress": deepcopy(self.progress), "error": self.error,
                    "log_revision": self.log_revision, "event_revision": self.event_revision,
                    "events": list(self.events), "sample_count": len(self.sample_labels),
                    "only_sample": self.sample_labels[0] if len(self.sample_labels) == 1 else None,
                    **({"logs": list(self.logs)} if include_logs else {}),
                    "cancel_requested": self.cancel_event.is_set()}

    def log_since(self, after: int) -> dict:
        with self.lock:
            first = self.log_revision - len(self.logs)
            reset = after < first or after > self.log_revision
            start = 0 if reset else after - first
            return {"lines": list(islice(self.logs, start, None)), "reset": reset,
                    "revision": self.log_revision, "limit": self.logs.maxlen}

    def log(self, text: str) -> None:
        with self.lock:
            for line in str(text).splitlines():
                self.logs.append(line[:4000])
                self.log_revision += 1

    def progressed(self, progress) -> None:
        with self.lock:
            self.progress = asdict(progress)
            if progress.phase:
                entry = {"phase": progress.phase, "workflow": progress.workflow,
                         "step_id": progress.step_id, "sample_ids": progress.sample_ids}
                if not self.events or entry != self.events[-1]["progress"]:
                    self.events.append({"at": _now(), "progress": entry})
                    self.event_revision += 1

    def outcome(self, outcome) -> None:
        with self.lock:
            self.run_dir = Path(outcome.run_dir)
            self.status = outcome.status


class GuiRunner(DockerComposeRunner):
    _startup_lock = threading.Lock()

    def __init__(self, prepared: PreparedAnalysis, job: Job):
        self.job = job
        super().__init__(prepared.layout, options=prepared.execution,
                         progress_callback=job.progressed, run_finished_callback=job.outcome)

        self._admission = DesktopAdmission(self._transport.metadata, job.id)
        self._step_scheduler = None

    def _project_idle(self, job_id):
        # Docker Compose labels scientific containers with our unique project.
        # Exited containers no longer consume the running quota.
        command = ["docker", "ps", "--all", "--quiet", "--filter",
                   "label=com.docker.compose.project=nipat-" + job_id]
        for status in ("created", "running", "restarting", "paused", "removing"):
            command.extend(["--filter", "status=" + status])
        environment = self._environment()
        try:
            result = subprocess.run(self._transport.command(command, environment), env=environment,
                                    stdin=subprocess.DEVNULL, capture_output=True, check=True,
                                    timeout=8, **background_process_options())
        except (OSError, subprocess.SubprocessError) as exc:
            message = ("Cannot confirm that the previous experiment has stopped. Check the runtime and retry."
                       if self.job.prepared.language == "en" else
                       "Impossibile verificare l’arresto dell’esperimento precedente. Controlla il runtime e riprova.")
            raise RuntimeExecutionError(message) from exc
        return not result.stdout.strip()

    def _cancel_point(self) -> None:
        if self.job.cancel_event.is_set():
            raise KeyboardInterrupt("Analisi annullata dall’utente.")

    def _base_command(self):
        # Compose project-scoped operations must never treat another run's
        # scientific container as an orphan, even with custom Compose settings.
        return [*super()._base_command(), "--project-name", "nipat-" + self.job.id]

    def _ensure_backend(self) -> None:
        if self.dry_run or self._backend_ready or self._transport.backend == "native":
            return super()._ensure_backend()
        # WSL and Lima startup helpers take bounded, exclusive runtime locks.
        # Wait locally for other GUI startups; release before scientific work.
        while not self._startup_lock.acquire(timeout=0.2):
            self._cancel_point()
        try:
            self._cancel_point()
            super()._ensure_backend()
        finally:
            self._startup_lock.release()

    def _write(self, text, *, terminal=True, log=True):
        self.job.log(text)
        # Preserve the native execution log without printing to a hidden console.
        with self._write_lock:
            if log and self._log is not None:
                self._log.write(str(text))
                self._log.flush()

    def _preparation_progress(self, phase, completed=None, total=None):
        self.job.progressed(ProgressSnapshot(
            status="running", elapsed_seconds=max(0, time.monotonic() - self.job.started_monotonic),
            phase=phase, sample_ids=(), completed=completed, total=total,
            unit="bytes" if total is not None else None))

    def _prepare_runtime(self):
        self._cancel_point()
        self._preparation_progress("preparing-runtime")
        result = super()._prepare_runtime()
        self._cancel_point()
        return result

    def _describe_bundled_engine(self):
        self._step_scheduler = None
        self._cancel_point()
        self._preparation_progress("verifying-engine")
        result = super()._describe_bundled_engine()
        self._cancel_point()
        if (self._bundled_workflow == "workflow-plan-all" and self._record is not None
                and result.get("desktop_scheduling") == DesktopStepScheduler.interface):
            data = self._record.data
            assigned = data["concurrent_execution"]
            if assigned["assigned_cpus"] is not None and assigned["assigned_memory_mib"] is not None:
                directory = self._record.run_dir / "work" / "desktop-scheduling"
                directory.mkdir()
                self._step_scheduler = DesktopStepScheduler(
                    self._admission, directory, data["resource_snapshot"], self.options,
                    queued=self.job.queued_siblings, runtime_idle=self._project_idle,
                )
                assigned["step_scheduling"] = {"interface": DesktopStepScheduler.interface,
                                               "grants": "work/desktop-scheduling/grants.jsonl"}
        return result

    def _record_resource_snapshot(self):
        super()._record_resource_snapshot()
        if self.dry_run or self._record is None:
            return
        from nipat.resources import fixed_execution_budget

        data = self._record.data
        snapshot = data["resource_snapshot"]
        capacity = fixed_execution_budget(snapshot)
        cpu, memory = capacity["cpu_limit"], capacity["memory_capacity_mib"]
        requested = self.options
        waiting = False
        while True:
            self._cancel_point()
            allocation = self._admission.try_admit(cpu, memory, requested, self._project_idle,
                                                   queued=self.job.queued_siblings())
            if allocation is not None:
                break
            if not waiting:
                self._preparation_progress("waiting-for-resources")
                waiting = True
            self.job.cancel_event.wait(0.3)
        self.job.admission_ready()
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
        self._record.save()

    def _hash_progress(self, path, completed, total):
        self._cancel_point()
        self._preparation_progress("checking-inputs", completed, total)
        super()._hash_progress(path, completed, total)

    def _finalize_status(self, record, status):
        # The last input hash is still cancellable. Once a terminal result is
        # chosen, reject later stop requests while its report is being written.
        with self.job.lock:
            if status in {"planned", "succeeded"}:
                self._cancel_point()
            super()._finalize_status(record, status)
            self.job.status = "finalizing"

    @contextmanager
    def record_run(self, run_dir, *args, **kwargs):
        with self.job.lock:
            self.job.run_dir = Path(run_dir)
        gui = {"schema_version": 1, "name": self.job.name,
               "draft": deepcopy(self.job.prepared.draft),
               "execution": self.options.as_dict(),
               "scientific_settings": deepcopy(self.job.prepared.preview["effective_settings"])}
        with (Path(run_dir) / "gui.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(gui, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
        registration = nullcontext() if self.dry_run else self._admission.registration()
        with registration, super().record_run(run_dir, *args, **kwargs) as record:
            self._cancel_point()
            self.job.prepared.assert_inputs_unchanged()
            yield record
            self._cancel_point()

    def run(self, *args, **kwargs):
        self._cancel_point()
        observer = nullcontext()
        if self._step_scheduler is not None:
            def report_error(exc):
                prefix = ("Desktop step scheduling interrupted" if self.job.prepared.language == "en"
                          else "Coordinamento delle risorse tra i passi interrotto")
                self._write(f"{prefix}: {exc}\n")
            observer = self._step_scheduler.observing(report_error)
        try:
            with observer:
                result = super().run(*args, **kwargs)
        except Exception:
            # Stopping the positively identified container unblocks stdout. Keep
            # the same interrupted status as the CLI's KeyboardInterrupt path.
            self._cancel_point()
            raise
        finally:
            if self._record is not None and self._record.data.get("commands"):
                stage = self._record.data["commands"][-1]
                cleanup = stage.get("container_cleanup", {}).get("status")
                if stage.get("started_at") and cleanup not in {"removed", "stopped", "absent"}:
                    self._admission.unconfirmed_cleanup = True
        self._cancel_point()
        return result


class JobManager:
    def __init__(self, *, runner_factory=GuiRunner, workflows_factory=Workflows,
                 reconcile=reconcile_run):
        self._runner_factory = runner_factory
        self._workflows_factory = workflows_factory
        self._reconcile = reconcile
        self._jobs: dict[str, Job] = {}
        self._pending: OrderedDict[str, Job] = OrderedDict()
        self._preparing: set[str] = set()
        self._finished: OrderedDict[str, None] = OrderedDict()
        self._lock = threading.RLock()

    def list(self, include_logs: bool = True) -> list[dict]:
        if type(include_logs) is not bool:
            raise ValidationError("Opzione registro non valida.")
        with self._lock:
            return [job.snapshot(include_logs=include_logs) for job in reversed(list(self._jobs.values()))]

    def active(self) -> dict:
        # The core may report its final status while it is still persisting the
        # report and closing resources. Wait for the worker's completion event.
        with self._lock:
            jobs = [job.snapshot(include_logs=False) for job in self._jobs.values() if not job.done.is_set()]
        return {"active": bool(jobs), "jobs": jobs}

    def get(self, job_id: str) -> dict:
        return self._get(job_id).snapshot()

    def logs(self, job_id: str, after: int = 0) -> dict:
        if type(after) is not int or after < 0:
            raise ValidationError("Posizione nel registro non valida.")
        return self._get(job_id).log_since(after)

    def _get(self, job_id: str) -> Job:
        if not isinstance(job_id, str):
            raise ValidationError("Identificativo dell’attività non valido.")
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise ValidationError("Attività non trovata in questa sessione.")
        return job

    def start(self, prepared: PreparedAnalysis) -> dict:
        prepared.assert_inputs_unchanged()
        with self._lock:
            # Keep completed observations bounded; persisted run.json is the archive.
            while len(self._jobs) >= 100 and self._finished:
                job_id, _ = self._finished.popitem(last=False)
                del self._jobs[job_id]
            job = Job(prepared, self)
            job.status = "queued"
            self._jobs[job.id] = job
            self._pending[job.id] = job
            self._dispatch()
        return job.snapshot()

    def waiting_to_prepare(self) -> int:
        with self._lock:
            return len(self._pending)

    def preparation_finished(self, job_id: str) -> None:
        with self._lock:
            self._preparing.discard(job_id)
            self._dispatch()

    def _dispatch(self) -> None:
        # Only two supervisors at a time may hash inputs or wait for initial
        # admission. Once admitted, a calculation frees its preparation slot.
        # Scientific concurrency is governed separately by the runtime budget.
        while self._pending and len(self._preparing) < 2:
            job_id, job = self._pending.popitem(last=False)
            job.thread = threading.Thread(target=self._execute, args=(job,),
                                          name="nipat-analysis-" + job.id[:8], daemon=False)
            self._preparing.add(job_id)
            try:
                job.thread.start()
            except RuntimeError as exc:
                job.thread = None
                self._preparing.discard(job_id)
                if any(other.thread is not None and not other.done.is_set() for other in self._jobs.values()):
                    self._pending[job_id] = job
                    self._pending.move_to_end(job_id, last=False)
                    return  # Retry on the next admission or completion.
                with job.lock:
                    job.status = "failed"
                    job.error = str(exc)
                    self._mark_finished(job)

    def _mark_finished(self, job: Job) -> None:
        # Called with both the manager and job locks held.
        job.finished_at = _now()
        self._finished[job.id] = None
        job.done.set()

    def finished_for(self, path: Path) -> str | None:
        with self._lock:
            return next((job.id for job in self._jobs.values()
                         if job.done.is_set() and job.run_dir == path), None)

    def discard(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                if not job.done.is_set():
                    raise ValidationError("Attendere la fine dell’esperimento prima di rimuovere la scheda.")
                self._finished.pop(job_id, None)
                del self._jobs[job_id]

    def _execute(self, job: Job) -> None:
        try:
            if job.cancel_event.is_set():
                raise KeyboardInterrupt("Analisi annullata prima dell’avvio.")
            with job.lock:
                if not job.cancel_event.is_set():
                    job.status = "starting"
            job.progressed(ProgressSnapshot(
                status="starting", elapsed_seconds=time.monotonic() - job.started_monotonic,
                phase="checking-inputs", sample_ids=()))
            job.prepared.assert_inputs_unchanged()
            runner = self._runner_factory(job.prepared, job)
            with job.lock:
                job.runner = runner
                if job.cancel_event.is_set():
                    raise KeyboardInterrupt("Analisi annullata prima dell’avvio.")
                job.status = "running"
            workflows = self._workflows_factory(job.prepared.layout, runner,
                                                job.prepared.scientific_settings)
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            run_dir = workflows.analyze(caller=job.prepared.draft["caller"], analyses=[],
                                        run_name=f"analysis-{stamp}-{job.id[:8]}",
                                        **deepcopy(job.prepared.inputs))
            with job.lock:
                job.run_dir = Path(run_dir)
                job.status = read_run_status(job.run_dir)
                if job.status not in _TERMINAL:
                    job.status = "failed"
                    job.error = "Il risultato finale non è verificabile: consultare il registro dell’esperimento."
        except KeyboardInterrupt as exc:
            with job.lock:
                job.status = "interrupted"
                job.error = str(exc) or "Analisi annullata."
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.error = str(exc) or type(exc).__name__
        finally:
            with self._lock:
                with job.lock:
                    if job.runner is not None and job.runner.last_run_dir is not None:
                        job.run_dir = job.runner.last_run_dir
                    self._mark_finished(job)
                self.preparation_finished(job.id)

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            job = self._get(job_id)
            if self._pending.pop(job_id, None) is not None:
                with job.lock:
                    job.cancel_event.set()
                    job.status = "interrupted"
                    self._mark_finished(job)
                return job.snapshot()
        with job.lock:
            if job.status == "finalizing" or job.status in _TERMINAL:
                return job.snapshot()
            if job.cancel_event.is_set():
                return job.snapshot()
            job.cancel_event.set()
            job.status = "cancel_requested"
            job.log("Annullamento richiesto: attendo l’arresto sicuro e il salvataggio dei risultati disponibili.")
        threading.Thread(target=self._stop_owned, args=(job,),
                         name="nipat-stop-" + job.id[:8], daemon=True).start()
        return job.snapshot()

    def _stop_owned(self, job: Job) -> None:
        last_message = None
        while not job.done.wait(0.5):
            with job.lock:
                runner, path = job.runner, job.run_dir
            if runner is None or path is None:
                continue
            try:
                # Core reconciliation verifies backend, run labels, immutable
                # container ID and image before touching any runtime process.
                observation = self._reconcile(runner, path, stop=False)
                owned = [item for item in observation.get("containers", [])
                         if item.get("owned") and item.get("state") in
                         {"created", "running", "restarting", "paused", "exited", "dead"}]
                if owned:
                    stopped = self._reconcile(runner, path, stop=True)
                    outcomes = [item.get("cleanup", {}).get("status")
                                for item in stopped.get("containers", [])
                                if item.get("owned") and item.get("state") in
                                {"created", "running", "restarting", "paused", "exited", "dead"}]
                    if outcomes and all(status in {"removed", "stopped", "absent"} for status in outcomes):
                        return
                    message = "Il runtime non ha ancora confermato l’arresto; riprovo."
                    if message != last_message:
                        job.log(message)
                        last_message = message
            except Exception as exc:
                message = str(exc)
                if message != last_message:
                    job.log("Arresto in attesa di conferma del runtime: " + message)
                    last_message = message
            job.done.wait(1)

    def wait(self, job_id: str, timeout: float | None = None) -> dict:
        """For shutdown and tests; RPC uses nonblocking jobs.get instead."""
        job = self._get(job_id)
        job.done.wait(timeout)
        return job.snapshot()
