"""Validate observed scientific worker events without loading reference oracles.

Shared by installed workflow checks and the independent equivalence harness.
This module only inspects retained execution evidence; it runs no analysis and
has no dependency on frozen scientific sources or test fixtures.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_parallel_execution(directory: Path, *, mode: str, cap: int | None,
                              require_parallel: bool, require_overlap: bool = True,
                              admission_only: bool = False) -> dict:
    """Require real scientific worker events, concurrency and respected limits.

    A requested pool size alone is not evidence that a workflow used it. Each
    process writes its own events; only matching actual child task intervals
    establish simultaneous execution. Scientific output equality is checked
    independently of these nondeterministically ordered diagnostic records.
    """
    events = []
    files = sorted(directory.glob("worker-*.jsonl"))
    if not files:
        raise ValueError("Parallel qualification has no actual scientific worker events")
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if value.get("interface") != "nipat-parallel-v1" or value.get("schema_version") != 1:
                raise ValueError("Invalid scientific worker event schema")
            events.append(value)
    plans = [event for event in events if event.get("event") == "plan"]
    if not plans:
        raise ValueError("Parallel qualification has no worker plans")
    for plan in plans:
        workers, tasks = plan.get("workers"), plan.get("tasks")
        if (type(workers) is not int or type(tasks) is not int or tasks < 0
                or not 1 <= workers <= max(1, tasks) or plan.get("mode") != mode):
            raise ValueError("Invalid effective scientific worker count")
        cpu, memory = plan.get("cpu_limit"), plan.get("memory_worker_limit")
        if (type(cpu) not in (int, float) or not math.isfinite(cpu) or cpu <= 0
                or type(memory) not in (int, float) or not math.isfinite(memory) or memory < 1
                or workers > math.ceil(cpu) or workers > memory
                or (cap is not None and workers > cap)):
            raise ValueError("Scientific worker plan exceeded CPU, memory or requested process budget")
        if mode == "serial" and workers != 1:
            raise ValueError("Serial scientific execution created a parallel plan")
    budget_fields = ("workers", "tasks", "mode", "cpu_limit", "memory_worker_limit")
    current_plans = {}
    completed = set()
    pending = {}
    intervals = []
    for sequence, event in enumerate(sorted(events, key=lambda item: item.get("observed_at_unix", -1))):
        owner = (event.get("coordinator_pid"), event.get("label"))
        signature = tuple(event.get(name) for name in budget_fields)
        if event.get("event") == "plan":
            current_plans[owner] = (sequence, signature)
            continue
        if event.get("event") not in {"task-start", "task-end"}:
            continue
        pid, coordinator = event.get("pid"), event.get("coordinator_pid")
        stamp, index = event.get("observed_at_unix"), event.get("task_index")
        if (not isinstance(pid, int) or not isinstance(coordinator, int)
                or not isinstance(stamp, (int, float)) or not math.isfinite(stamp)
                or type(index) is not int):
            raise ValueError("Invalid observed scientific task identity or time")
        plan = current_plans.get(owner)
        if plan is None or signature != plan[1]:
            raise ValueError("Scientific worker task has no matching resource plan")
        task = (plan[0], index)
        key = (task, pid)
        if not 1 <= index <= event["tasks"]:
            raise ValueError("Scientific task index is outside its resource plan")
        if event["event"] == "task-start":
            if key in pending:
                raise ValueError("Scientific worker task starts twice without ending")
            pending[key] = (stamp, event["workers"])
        else:
            if key not in pending or stamp < pending[key][0]:
                raise ValueError("Scientific worker task has no matching start")
            if event.get("outcome") != "succeeded":
                raise ValueError("Scientific worker task did not succeed")
            if task in completed:
                raise ValueError("Scientific worker task completed twice in the same invocation")
            completed.add(task)
            started, workers = pending.pop(key)
            if workers != event["workers"]:
                raise ValueError("Scientific worker task changed its resource plan")
            if pid != coordinator:
                intervals.append((started, stamp, pid, coordinator, workers))
    if pending:
        raise ValueError("Scientific worker tasks did not finish")
    child_pids = sorted({value[2] for value in intervals})
    if mode == "serial" and child_pids:
        raise ValueError("Serial scientific execution used child workers")
    # A declared pool size is not proof of respecting it. Count actual child
    # intervals, including children of different coordinators, so an accidental
    # nested pool cannot hide behind individually valid resource plans. End
    # events precede starts at a shared timestamp; touching intervals do not
    # overlap. Serial nested callbacks have pid == coordinator and are not
    # counted twice as additional processes.
    boundaries = []
    for number, (started, finished, *_rest) in enumerate(intervals):
        if finished > started:
            boundaries.extend(((started, 1, number), (finished, -1, number)))
    active = {}
    maximum_observed = 0
    maximum_planned = max(plan["workers"] for plan in plans)
    overlap = False
    for _stamp, delta, number in sorted(boundaries):
        if delta == -1:
            del active[number]
            continue
        active[number] = intervals[number]
        live_pids = {value[2] for value in active.values()}
        maximum_observed = max(maximum_observed, len(live_pids))
        # The currently active outer pool owns the budget. A larger plan in a
        # different (possibly later) phase cannot authorize extra descendants
        # now. A nested coordinator is itself one of these live child PIDs.
        outer_budgets = [value[4] for value in active.values() if value[3] not in live_pids]
        if not outer_budgets:
            raise ValueError("Scientific worker coordinator ancestry is cyclic")
        shared_limit = min(outer_budgets)
        if len(live_pids) > shared_limit or (cap is not None and len(live_pids) > cap):
            raise ValueError("Observed scientific workers exceeded the shared process budget")
        for value in active.values():
            siblings = {item[2] for item in active.values() if item[3] == value[3]}
            if len(siblings) > value[4]:
                raise ValueError("Observed scientific workers exceeded their coordinator's process budget")
            overlap = overlap or len(siblings) > 1
    if require_parallel and len(child_pids) < 2:
        raise ValueError("Scientific parallel qualification did not observe two actual child workers")
    if require_parallel and require_overlap and not overlap:
        raise ValueError("Scientific parallel qualification did not observe two simultaneous child workers")
    # The same stage can be invoked more than once (e.g. one cutoff per family).
    # Every invocation promises one result for each one-based task index.
    # A single-worker SNP admission hands execution to the inner sample runner.
    if admission_only and (len(events) != 1 or plans[0]["workers"] != 1 or require_parallel):
        raise ValueError("Expected only a single-worker admission plan")
    expected_tasks = 0 if admission_only else sum(plan["tasks"] for plan in plans)
    if len(completed) != expected_tasks:
        raise ValueError("Scientific worker evidence has missing completed tasks")
    return {"event_sha256": {path.name: _digest(path) for path in files},
            "observed_child_pids": child_pids, "simultaneous_child_workers": overlap,
            "maximum_planned_workers": maximum_planned,
            "maximum_observed_child_workers": maximum_observed,
            "requested_mode": mode, "requested_max_workers": cap,
            "overlapping_workers_required": require_parallel and require_overlap,
            "plans": plans}
