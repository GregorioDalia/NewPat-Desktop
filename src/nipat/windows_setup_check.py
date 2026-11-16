"""Run an installer check in a private Windows job using the bundled Python."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys
import time


_JOB_ACCOUNTING = 1
_JOB_EXTENDED_LIMITS = 9
_KILL_ON_JOB_CLOSE = 0x2000
_PROCESS_TERMINATE_AND_SET_QUOTA = 0x0101
_TIMEOUT = 124


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time_limit", ctypes.c_longlong),
        ("job_time_limit", ctypes.c_longlong),
        ("flags", wintypes.DWORD),
        ("minimum_working_set", ctypes.c_size_t),
        ("maximum_working_set", ctypes.c_size_t),
        ("active_process_limit", wintypes.DWORD),
        ("affinity", ctypes.c_size_t),
        ("priority_class", wintypes.DWORD),
        ("scheduling_class", wintypes.DWORD),
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicLimits),
        ("io_counters", ctypes.c_ulonglong * 6),
        ("process_memory_limit", ctypes.c_size_t),
        ("job_memory_limit", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class Accounting(ctypes.Structure):
    _fields_ = [
        ("user_time", ctypes.c_longlong),
        ("kernel_time", ctypes.c_longlong),
        ("period_user_time", ctypes.c_longlong),
        ("period_kernel_time", ctypes.c_longlong),
        ("page_faults", wintypes.DWORD),
        ("total_processes", wintypes.DWORD),
        ("active_processes", wintypes.DWORD),
        ("terminated_processes", wintypes.DWORD),
    ]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean = wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL
    pointer = ctypes.c_void_p
    for name, arguments, result in (
        ("CreateJobObjectW", (pointer, wintypes.LPCWSTR), handle),
        ("SetInformationJobObject", (handle, ctypes.c_int, pointer, dword), boolean),
        ("QueryInformationJobObject", (handle, ctypes.c_int, pointer, dword, pointer), boolean),
        ("OpenProcess", (dword, boolean, dword), handle),
        ("AssignProcessToJobObject", (handle, handle), boolean),
        ("TerminateJobObject", (handle, wintypes.UINT), boolean),
        ("CloseHandle", (handle,), boolean),
    ):
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


def _wait_empty(kernel, job, deadline: float) -> bool:
    accounting = Accounting()
    while True:
        if not kernel.QueryInformationJobObject(
            job, _JOB_ACCOUNTING, ctypes.byref(accounting), ctypes.sizeof(accounting), None
        ):
            raise ctypes.WinError()
        if accounting.active_processes == 0:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.05, remaining))


def supervise(command: list[str], timeout: int) -> int:
    kernel = _kernel()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError()
    worker = None
    attached = False
    try:
        limits = ExtendedLimits()
        limits.basic.flags = _KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(
            job, _JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise ctypes.WinError()
        deadline = time.monotonic() + timeout
        # The worker cannot launch the command until it receives one byte.
        # If the supervisor dies before assignment, the worker reads EOF.
        worker = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-u", str(Path(__file__).resolve()), "--worker", *command],
            stdin=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        with worker.stdin as start_signal:
            process = kernel.OpenProcess(_PROCESS_TERMINATE_AND_SET_QUOTA, False, worker.pid)
            if not process:
                raise ctypes.WinError()
            try:
                if not kernel.AssignProcessToJobObject(job, process):
                    raise ctypes.WinError()
                attached = True
            finally:
                kernel.CloseHandle(process)
            start_signal.write(b"1")
        try:
            code = worker.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            return _TIMEOUT
        return code if _wait_empty(kernel, job, deadline) else _TIMEOUT
    finally:
        try:
            if attached and not _wait_empty(kernel, job, time.monotonic()):
                if not kernel.TerminateJobObject(job, _TIMEOUT):
                    raise ctypes.WinError()
                if not _wait_empty(kernel, job, time.monotonic() + 5):
                    raise OSError("Arresto del controllo di preparazione non confermato.")
        finally:
            kernel.CloseHandle(job)
            if worker is not None and worker.poll() is None:
                worker.kill()
                worker.wait(timeout=5)


def main() -> int:
    if sys.argv[1:2] == ["--worker"]:
        if sys.stdin.buffer.read(1) != b"1":
            return 1
        return subprocess.call(
            sys.argv[2:], stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW
        )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("timeout", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not 1 <= args.timeout <= 86400 or not command:
        parser.error("Specificare un timeout valido e il controllo da eseguire.")
    try:
        return supervise(command, args.timeout)
    except (OSError, subprocess.SubprocessError) as error:
        print(f"NewPat: supervisione del controllo non riuscita: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
