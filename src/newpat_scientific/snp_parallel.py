"""Bound independent SNP samples to the shared R budget, with isolated workers.

Only the coordinator writes workflow-state.json. Each fresh Python worker owns
one step and one process group, including its R and samtools descendants.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zlib

from newpat_scientific.errors import PlanExecutionError, ValidationError
from newpat_scientific.panels import (read_bam_dictionary, read_snp_positions, reference_lengths,
                                     require_bam_targets, require_reference_windows)
from newpat_scientific.parallel import THREAD_LIMITS
from newpat_scientific.settings import normalize_settings

_STARTED = time.monotonic()
_STATE_READ_ATTEMPTS = 20
_STATE_READ_DELAY = 0.05

def _utc():
    return datetime.now(timezone.utc).isoformat()


def _event(directory, event, budget, coordinator, index=None, outcome=None):
    payload = {"schema_version": 1, "interface": "nipat-parallel-v1", "event": event,
               "label": "snp-samples", "coordinator_pid": coordinator, "pid": os.getpid(),
               "task_index": index, "outcome": outcome, "observed_at_unix": time.time(),
               "elapsed_seconds": time.monotonic() - _STARTED, **budget}
    with (directory / f"worker-{os.getpid()}.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, allow_nan=False, separators=(",", ":")) + "\n")


_MIB = 1024 * 1024
# Includes the fresh Python worker, the R scientific packages and plotting.
# Subsequent allowances size the arrays created from rows/observations. These
# are scheduling estimates, never a change to scientific depth or read filters.
_SAMPLE_BASE_BYTES = 768 * _MIB
_BYTES_PER_OBSERVATION = 2048
_SMALL_BAM_LIMIT = 1024 * 1024
_MAX_PROBE_SITES = 2048
_PROBE_SECONDS = 5
_PROBE_DEPTH = 2048
_MAX_BOUNDED_DEPTH = 8000


def _small_bam_records(path):
    """Bound record count by uncompressed bytes; never scan a large BAM."""
    if path.stat().st_size > _SMALL_BAM_LIMIT:
        return None
    try:
        with gzip.open(path, "rb") as stream:
            data = stream.read(_SMALL_BAM_LIMIT + 1)
    except (OSError, EOFError, zlib.error):
        return None
    if len(data) > _SMALL_BAM_LIMIT or not data.startswith(b"BAM\x01"):
        return None
    # Each alignment has a four-byte block length and a 32-byte fixed core.
    # Counting the header and variable fields as potential cores overestimates.
    return len(data) // 36


class _ProbeWindow:
    """Use the production runner's group cancellation for optional measurement."""
    def __init__(self, cancellation):
        self.cancellation = cancellation
        self.deadline = time.monotonic() + _PROBE_SECONDS

    @property
    def signum(self):
        return self.cancellation.signum or (signal.SIGTERM if time.monotonic() >= self.deadline else None)

    @property
    def exit_code(self):
        return self.cancellation.exit_code if self.cancellation.signum else 124


def _indexed_observations(source, positions, reference, directory, identifier, probe):
    """Measure each three-base window; overlapping windows may overcount."""
    from newpat_scientific.executor import _run_process

    if len(positions) > _MAX_PROBE_SITES or probe.signum is not None:
        return None
    indexes = [p for ext in (".bai", ".csi")
               for p in (Path(str(source) + ext), source.with_suffix(ext)) if p.is_file()]
    if not indexes or any(p.stat().st_mtime_ns < source.stat().st_mtime_ns for p in indexes):
        return None
    header = directory / f"coverage-{identifier}.sam"
    log = directory / f"coverage-{identifier}.log"
    if _run_process(["samtools", "view", "--no-PG", "-H", "-o", str(header), str(source)],
                    directory, log, probe) or probe.signum is not None:
        return None
    sequences, sorted_header = read_bam_dictionary(header, source)
    if not sorted_header:
        return None
    require_bam_targets(source, sequences, {chrom for chrom, _ in positions}, reference)
    bed = directory / f"coverage-{identifier}.bed"
    output = directory / f"coverage-{identifier}.tsv"
    with bed.open("x", encoding="utf-8") as handle:
        for chrom, position in positions:
            handle.write(f"{chrom}\t{position - 2}\t{position + 1}\n")
    # Include all mapped flags and leave D/N included. The extra count covers
    # all accepted alignments at the window. Well before the probe can clip
    # depth, retreat to one sample; scientific mpileup keeps its own settings.
    command = ["samtools", "bedcov", "-g", "0x704", "-c", "--max-depth", str(_PROBE_DEPTH),
               str(bed), str(source)]
    if _run_process(command, directory, output, probe) or probe.signum is not None:
        return None
    total = peak = count = 0
    with output.open(encoding="utf-8") as rows:
        for row in rows:
            fields = row.rstrip("\n").split("\t")
            if count >= len(positions) or len(fields) != 5:
                return None
            chrom, position = positions[count]
            if fields[:3] != [chrom, str(position - 2), str(position + 1)] or not all(
                    x.isdecimal() for x in fields[3:]):
                return None
            coverage, reads = map(int, fields[3:])
            if reads >= _PROBE_DEPTH // 2 or coverage > 3 * reads:
                return None
            total += coverage
            peak = max(peak, reads)
            count += 1
    return (total, peak) if count == len(positions) else None


def _sample_estimate(step, source, directory, cancellation):
    parameters = step["parameters"]
    bam = parameters["mode"] == "bam"
    positions = read_snp_positions(Path(step["inputs"]["panel"]), for_bed=bam)
    input_bytes = source.stat().st_size
    # Materialized R tables and plots grow with panel size even at zero depth.
    base = _SAMPLE_BASE_BYTES + 8192 * len(positions)
    evidence = {"input_bytes": input_bytes, "panel_sites": len(positions)}
    if not bam:
        # Plain-text pileups are already expanded. Charge a generous per-byte
        # multiplier for token vectors, joins, read groups and fallback parsing.
        return base + 512 * input_bytes, {**evidence, "basis": "pileup-bytes"}
    reference = reference_lengths(Path(step["inputs"]["reference"] + ".fai"))
    targets = require_reference_windows(reference, ((chrom, pos - 1, pos + 1) for chrom, pos in positions))
    reference_bytes = max(targets.values())
    depth = normalize_settings("snp-call", parameters.get("scientific_settings"))["max_depth"]
    evidence.update(max_depth=depth, largest_target_contig=reference_bytes)
    records = _small_bam_records(source)
    if records is not None:
        peak = min(records, depth) if depth else records
        basis = "small-bam-uncompressed-record-bound"
    elif 0 < depth <= _MAX_BOUNDED_DEPTH:
        peak = depth
        basis = "configured-bam-depth"
    else:
        peak = None
    observations = None if peak is None else 3 * len(positions) * peak
    # A whole-file/depth upper bound is enough for small jobs. Across a large
    # sparse panel it can overstate the workload by orders of magnitude.
    if observations is None or observations * _BYTES_PER_OBSERVATION > _SAMPLE_BASE_BYTES:
        measured = _indexed_observations(source, positions, reference, directory, step["id"], cancellation)
        if measured is not None:
            observations, peak = measured
            basis = "indexed-window-coverage"
    if observations is None:
        return None, {**evidence, "basis": "bam-coverage-unavailable"}
    # The largest referenced chromosome can be resident during acquisition.
    # Allow for read buffers independently of R's expanded observations.
    size = base + 2 * reference_bytes + 16384 * peak + _BYTES_PER_OBSERVATION * observations
    return size, {**evidence, "basis": basis, "observations": observations, "peak_depth_bound": peak}


def _query_budget(steps, samples, directory, cancellation):
    from newpat_scientific.executor import _run_process

    estimates = {}
    probe = _ProbeWindow(cancellation)
    for step in steps:
        if cancellation.signum is not None:
            raise KeyboardInterrupt
        source = Path(samples[step["inputs"]["sample"]])
        try:
            size, evidence = _sample_estimate(step, source, directory, probe)
        except (OSError, ValidationError, UnicodeError):
            # Normal execution retains the detailed scientific/input error.
            size, evidence = None, {"basis": "sample-size-unavailable"}
        estimates[step["id"]] = {**evidence, "memory_mib": (size + _MIB - 1) // _MIB if size else None}
    if cancellation.signum is not None:
        raise KeyboardInterrupt
    sizes = [item["memory_mib"] for item in estimates.values() if item["memory_mib"] is not None]
    # R sets the CPU ceiling and the minimum charge for a loaded worker.
    # An outer pool is possible only when two workloads have been estimated.
    memory = str(min(sizes)) if len(sizes) >= 2 else "unknown"
    tasks = len(steps)
    expression = ('a <- commandArgs(TRUE); source(a[[1]]); observed <- a[[3]] != "unknown"; '
                  'm <- if (observed) as.numeric(a[[3]]) else NULL; '
                  'cat(jsonlite::toJSON(nipat_parallel_budget(as.integer(a[[2]]), '
                  'memory_mib=m, workload_observed=observed), auto_unbox=TRUE, null="null", digits=NA))')
    target = directory / "budget.json"
    code = _run_process(["Rscript", "-e", expression, str(Path(__file__).with_name("parallel.R")), str(tasks), memory],
                        directory, target, cancellation)
    if cancellation.signum is not None:
        raise KeyboardInterrupt
    if code:
        raise PlanExecutionError("execution.parallel_budget", "Cannot determine the shared SNP process budget; see parallel/snp/budget.json.")
    try:
        budget = json.loads(target.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise PlanExecutionError("execution.parallel_budget", "The R process budget is invalid.") from exc
    if (not isinstance(budget, dict) or type(budget.get("workers")) is not int
            or not 1 <= budget["workers"] <= tasks or budget.get("tasks") != tasks
            or (memory == "unknown" and budget["workers"] != 1)):
        raise PlanExecutionError("execution.parallel_budget", "The R process budget is inconsistent with the batch.")
    costs = {}
    if budget["workers"] > 1:
        capacity, rss, floor = (budget.get(key) for key in
                                ("memory_budget_mib", "coordinator_rss_mib", "memory_per_worker_mib"))
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
               for value in (capacity, rss, floor)):
            raise PlanExecutionError("execution.parallel_budget", "The R process budget lacks a usable memory limit.")
        remaining = max(0, math.floor(capacity - rss))
        charges = sorted(max(math.ceil(floor), size) for size in sizes)
        used = slots = 0
        for charge in charges:
            if used + charge > remaining or slots == budget["workers"]:
                break
            used += charge
            slots += 1
        if slots < budget["workers"]:
            budget["reason"] = "workload-memory-budget"
        budget.update(workers=max(1, slots), sample_budget_mib=remaining)
        for identifier, item in estimates.items():
            size = item["memory_mib"]
            charge = max(math.ceil(floor), size) if size is not None else None
            # A sample that cannot share with even the smallest runs alone and
            # retains the ordinary inner R/samtools budget.
            costs[identifier] = charge if charge is not None and charge + charges[0] <= remaining else None
            item["charge_mib"] = charge
            item["exclusive"] = costs[identifier] is None
    (directory / "sample-estimates.json").write_text(json.dumps(estimates, indent=2), encoding="utf-8")
    target.write_text(json.dumps(budget, indent=2), encoding="utf-8")
    return budget, costs


def _kill_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin can retain an exited group's zombies and return EPERM when
        # no signalable members remain. Never hide denial for a live worker
        # or on platforms where this is not the exited-group convention.
        if sys.platform != "darwin" or process.poll() is None:
            raise


def _stop_workers(active):
    # Python receives SIGTERM as cancellation while R/samtools receive it in
    # their inherited group. SIGKILL also reaches any stubborn grandchildren.
    for process, _record, _path, _log in active.values():
        _kill_group(process, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while any(item[0].poll() is None for item in active.values()) and time.monotonic() < deadline:
        time.sleep(0.05)
    for process, _record, _path, log in active.values():
        _kill_group(process, signal.SIGKILL)
        process.wait()
        log.close()


def _merge_record(record, path, *, attempts=_STATE_READ_ATTEMPTS):
    """Read a stopped worker's final record, without accepting a stale snapshot.

    Host-backed mounts may briefly delay visibility of the last replacement.
    Retry only read/decoding failures, with at most 0.95 seconds of delay.
    Identity errors are permanent and must never be merged or retried.
    """
    for attempt in range(attempts):
        try:
            updated = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError) as exc:
            if attempt + 1 == attempts:
                raise PlanExecutionError(
                    "execution.worker_state",
                    f"Cannot read completed SNP step state {path.name} after {attempts} attempt(s): "
                    f"{type(exc).__name__}: {exc}",
                ) from exc
            time.sleep(_STATE_READ_DELAY)
    if (not isinstance(updated, dict) or updated.get("id") != record["id"]
            or updated.get("workflow") != "snp-call"
            or updated.get("script_sha256") != record["script_sha256"]):
        raise PlanExecutionError("execution.worker_state", f"SNP step state {path.name} has a different identity.")
    record.clear()
    record.update(updated)


def execute_independent_snp_steps(plan, state, root, scripts, cancellation, *, atomic_json):
    """Run all ready SNP callers in a mixed plan within the global budget.

    Only the coordinator writes the global state. Fresh worker interpreters
    import the production step runner instead of serializing Python state.
    """
    records = {record["id"]: record for record in state["steps"]}
    steps = [step for step in plan["steps"] if step["workflow"] == "snp-call" and records[step["id"]]["status"] == "pending"]
    if (os.name != "posix" or len(steps) < 2
            or os.environ.get("NIPAT_EXECUTION_MODE", "auto") == "serial"
            or os.environ.get("NIPAT_MAX_WORKERS") == "1"
            or os.environ.get("NIPAT_PARALLEL_CHILD") == "1"):
        return False
    if cancellation.signum is not None:
        raise KeyboardInterrupt
    directory = root / "parallel" / "snp"
    directory.mkdir(parents=True)
    samples = {sample["id"]: sample["path"] for sample in plan["samples"]}
    budget, costs = _query_budget(steps, samples, directory, cancellation)
    state["snp_parallel"] = {"interface": "nipat-parallel-v1", **budget,
                             "diagnostics": "parallel/snp"}
    _event(directory, "plan", budget, os.getpid())
    atomic_json(root / "workflow-state.json", state)
    if budget["workers"] == 1:
        return False
    environment = {**os.environ, **THREAD_LIMITS}
    module_root = str(Path(__file__).resolve().parent.parent)
    environment["PYTHONPATH"] = module_root + (os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else "")
    shared_environment = {**environment, "NIPAT_PARALLEL_CHILD": "1", "NIPAT_MAX_WORKERS": "1"}
    pending = {step["id"]: index for index, step in enumerate(steps, 1)}
    active = {}
    try:
        while pending or active:
            if cancellation.signum is not None:
                raise KeyboardInterrupt
            changed = False
            # Inspect all completed jobs before adding work: a failed sample
            # must not cause a fresh sample to start in the same polling cycle.
            for identifier, (process, record, record_path, log) in list(active.items()):
                code = process.poll()
                if code is None:
                    continue
                process.wait()
                # Intermediate states are worker-owned and may be replaced on
                # Windows/WSL host mounts. Progress already uses its own events;
                # only read the final state once its writer has exited.
                if code:
                    state["exit_code"] = code if code > 0 else 128 - code
                _merge_record(record, record_path)
                changed = True
                log.close()
                del active[identifier]
                if code or record.get("status") != "succeeded":
                    _kill_group(process, signal.SIGKILL)
                    if record.get("status") not in {"failed", "cancelled"}:
                        record.update(status="failed", exit_code=code if code > 0 else 2, finished_utc=_utc(),
                                      error={"code": "execution.worker", "message": "SNP worker exited without a successful result."})
                    state["exit_code"] = record.get("exit_code") or 2
                    atomic_json(root / "workflow-state.json", state)
                    raise PlanExecutionError("execution.process", f"{identifier}: isolated SNP worker failed; see parallel/snp/worker-{identifier}.log.")
            if active and not changed:
                time.sleep(0.05)
                continue
            available = budget["sample_budget_mib"] - sum(
                costs[identifier] or budget["sample_budget_mib"] for identifier in active)
            # Preserve plan indices. A later small sample may occupy unused
            # capacity while an earlier, larger one waits for its reservation.
            for identifier, index in list(pending.items()):
                if cancellation.signum is not None:
                    raise KeyboardInterrupt
                if len(active) >= budget["workers"] or available <= 0:
                    break
                charge = costs[identifier]
                if (charge is None and active) or (charge is not None and charge > available):
                    continue
                record = records[identifier]
                job = directory / f"job-{identifier}.json"
                record_path = directory / f"state-{identifier}.json"
                atomic_json(job, {"schema_version": 1, "root": str(root), "step_id": identifier,
                                  "record": record, "scripts": {key: str(value) for key, value in scripts.items()},
                                  "budget": budget, "coordinator_pid": os.getpid(), "task_index": index,
                                  "exclusive": charge is None})
                log = (directory / f"worker-{identifier}.log").open("xb")
                try:
                    process = subprocess.Popen([sys.executable, "-m", "newpat_scientific.snp_parallel", "--worker", str(job)],
                                               cwd=root, env=environment if charge is None else shared_environment,
                                               stdin=subprocess.DEVNULL,
                                               stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                except BaseException:
                    log.close()
                    raise
                active[identifier] = (process, record, record_path, log)
                record.update(status="running", started_utc=_utc())
                changed = True
                del pending[identifier]
                available -= charge if charge is not None else budget["sample_budget_mib"]
            if changed:
                atomic_json(root / "workflow-state.json", state)
            if active:
                time.sleep(0.05)
        return True
    finally:
        _stop_workers(active)
        for _process, record, record_path, _log in active.values():
            try:
                _merge_record(record, record_path, attempts=1)
            except PlanExecutionError as exc:
                # Keep the primary failure/cancellation and still finalize all
                # siblings if a killed worker could not commit a readable state.
                record["state_read_error"] = {"code": exc.code, "message": str(exc)}
            if record.get("status") in {"pending", "running"}:
                record.update(status="cancelled", exit_code=cancellation.exit_code, finished_utc=_utc(),
                              error={"code": "execution.stopped", "message": "Stopped with the SNP batch."})
        atomic_json(root / "workflow-state.json", state)


def _worker_process(command, cwd, log_path, cancellation):
    """Keep every command in the worker's group, which its coordinator owns."""
    with log_path.open("xb") as output:
        process = subprocess.Popen(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=False)
        try:
            while True:
                if cancellation.signum is not None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    return cancellation.exit_code
                try:
                    code = process.wait(timeout=0.05)
                    return code if code >= 0 else 128 - code
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.wait()
            raise


def _worker(job_path):
    from newpat_scientific.executor import _atomic_json, _Cancellation, _execute_step

    job = json.loads(job_path.read_text(encoding="utf-8"))
    root = Path(job["root"])
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    step = next(item for item in plan["steps"] if item["id"] == job["step_id"])
    record = job["record"]
    state_path = job_path.parent / f"state-{step['id']}.json"
    cancellation = _Cancellation()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, cancellation.receive)
    os.environ.update(THREAD_LIMITS)
    if not job["exclusive"]:
        os.environ.update(NIPAT_PARALLEL_CHILD="1", NIPAT_MAX_WORKERS="1")
    _event(job_path.parent, "task-start", job["budget"], job["coordinator_pid"], job["task_index"])
    try:
        _execute_step(plan, step, record, root, {key: Path(value) for key, value in job["scripts"].items()},
                      {sample["id"]: sample for sample in plan["samples"]}, {}, cancellation,
                      lambda command, cwd, log: _worker_process(command, cwd, log, cancellation),
                      lambda: _atomic_json(state_path, record))
    except KeyboardInterrupt:
        record.update(status="cancelled", exit_code=cancellation.exit_code, finished_utc=_utc(),
                      error={"code": "execution.cancelled", "message": "SNP worker was cancelled."})
    except Exception as exc:
        record.update(status="failed", exit_code=record.get("exit_code") or 2, finished_utc=_utc(),
                      error={"code": getattr(exc, "code", "execution.worker"), "message": str(exc)})
    finally:
        _atomic_json(state_path, record)
        _event(job_path.parent, "task-end", job["budget"], job["coordinator_pid"], job["task_index"], record["status"])
    return 0 if record["status"] == "succeeded" else record.get("exit_code") or 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    return _worker(parser.parse_args().worker)


if __name__ == "__main__":
    raise SystemExit(main())
