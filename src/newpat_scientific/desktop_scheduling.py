"""Exchange desktop resource grants only when a plan owns no active workers."""

import errno
import json
import math
import os
from pathlib import Path
import re
import time

from newpat_scientific.errors import PlanExecutionError


INTERFACE = "step-budget-v1"
_GRANT_TIMEOUT = 60
_ENVIRONMENT = ("NIPAT_FIXED_RESOURCE_BUDGET", "NIPAT_CPU_LIMIT", "NIPAT_MEMORY_LIMIT_MIB")


def _error(detail):
    return PlanExecutionError("execution.desktop_scheduling", detail)


def _read(path):
    if path.is_symlink():
        raise _error(f"Invalid desktop scheduling file: {path.name}.")
    try:
        with path.open(encoding="utf-8") as stream:
            value = json.load(stream)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise _error(f"Cannot read desktop scheduling file {path.name}.") from exc
    if (not isinstance(value, dict) or value.get("interface") != INTERFACE
            or not isinstance(value.get("token"), str) or not re.fullmatch("[0-9a-f]{32}", value["token"])):
        raise _error(f"Invalid desktop scheduling message in {path.name}.")
    return value


def _limit(budget, field, *, whole=False):
    value = budget.get(field)
    if (type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            or (whole and int(value) != value)):
        raise _error(f"Invalid desktop resource grant field {field}.")
    return int(value) if whole else value


def _effective_budget(initial, grant, environment):
    for value in (initial, grant):
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("interface") != "nipat-fixed-resources-v1"):
            raise _error("Invalid fixed desktop resource budget.")
    cpu = min(_limit(initial, "cpu_limit"), _limit(grant, "cpu_limit"))
    memory = min(_limit(initial, "memory_capacity_mib", whole=True), _limit(grant, "memory_capacity_mib", whole=True))
    for key in ("NIPAT_CPU_LIMIT", "NIPAT_MEMORY_LIMIT_MIB"):
        if environment[key] is not None:
            try:
                hard = float(environment[key])
            except ValueError as exc:
                raise _error(f"Invalid initial desktop limit {key}.") from exc
            if not math.isfinite(hard) or hard <= 0 or (key == "NIPAT_MEMORY_LIMIT_MIB" and not hard.is_integer()):
                raise _error(f"Invalid initial desktop limit {key}.")
            if key == "NIPAT_CPU_LIMIT":
                cpu = min(cpu, hard)
            else:
                memory = min(memory, int(hard))
    reserve = max(_reserve(initial), _reserve(grant))
    ceiling = min(_limit(initial, "worker_ceiling", whole=True), _limit(grant, "worker_ceiling", whole=True),
                  max(1, math.floor(cpu)))
    memory_budget = math.floor(memory * (1 - reserve))
    return {**grant, "cpu_limit": cpu, "worker_ceiling": ceiling, "memory_capacity_mib": memory,
            "memory_budget_mib": memory_budget, "memory_reserve_fraction": reserve,
            "memory_allocation_per_worker_mib": memory_budget / ceiling}


def _reserve(budget):
    value = budget.get("memory_reserve_fraction")
    if type(value) not in (int, float) or not 0 <= value < 1:
        raise _error("Invalid desktop memory reserve.")
    return value


class DesktopStepBudget:
    def __init__(self, directory, atomic_json):
        self.directory = Path(directory)
        self.atomic_json = atomic_json
        self.initial_environment = {key: os.environ.get(key) for key in _ENVIRONMENT}
        self.applied = set()

    def _acknowledge(self, token, cancellation):
        message = {"interface": INTERFACE, "token": token}
        deadline = time.monotonic() + 1
        while cancellation.signum is None:
            try:
                self.atomic_json(self.directory / "ack.json", message)
                return
            except OSError as exc:
                # Windows-backed mounts can briefly retain a read handle on the
                # prior acknowledgement. Retry only the same atomic publication.
                busy = exc.errno in (errno.EACCES, errno.EPERM, errno.EBUSY) or getattr(exc, "winerror", None) in (32, 33)
                if not busy or time.monotonic() >= deadline:
                    raise _error("Cannot publish the desktop scheduling acknowledgement.") from exc
                time.sleep(0.05)
        raise KeyboardInterrupt

    def boundary(self, cancellation):
        if cancellation.signum is not None:
            raise KeyboardInterrupt
        if not self.directory.is_absolute() or self.directory.is_symlink():
            raise _error("Invalid desktop scheduling directory.")
        request = _read(self.directory / "request.json")
        if request is None or request["token"] in self.applied:
            return None
        token = request["token"]
        self._acknowledge(token, cancellation)
        deadline = time.monotonic() + _GRANT_TIMEOUT
        while cancellation.signum is None:
            grant = _read(self.directory / "grant.json")
            if grant is not None and grant["token"] == token:
                try:
                    initial = json.loads(self.initial_environment["NIPAT_FIXED_RESOURCE_BUDGET"] or "null")
                except ValueError as exc:
                    raise _error("Invalid initial desktop resource budget.") from exc
                budget = _effective_budget(initial, grant.get("budget"), self.initial_environment)
                encoded = json.dumps(budget, allow_nan=False, separators=(",", ":"))
                os.environ.update(NIPAT_FIXED_RESOURCE_BUDGET=encoded, NIPAT_CPU_LIMIT=str(budget["cpu_limit"]),
                                  NIPAT_MEMORY_LIMIT_MIB=str(budget["memory_capacity_mib"]))
                self.applied.add(token)
                return {"token": token, "cpu_limit": budget["cpu_limit"],
                        "memory_capacity_mib": budget["memory_capacity_mib"], "worker_ceiling": budget["worker_ceiling"]}
            if time.monotonic() >= deadline:
                raise _error("Timed out waiting for the desktop resource grant.")
            time.sleep(0.1)
        raise KeyboardInterrupt

    def restore(self):
        if self.applied:
            for key, value in self.initial_environment.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
