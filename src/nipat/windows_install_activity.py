"""Validate an inherited setup lease without loading a custom Windows DLL.

Executed by the pinned, temporary embedded Python before modifying an installed
runtime. Only standard-library modules are imported. The PowerShell caller owns
the actual FileStream and named event for its entire lifetime.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
import sys


class ProcessEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def _kernel():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for name, arguments, result in (
        ("CreateToolhelp32Snapshot", (wintypes.DWORD, wintypes.DWORD), wintypes.HANDLE),
        ("Process32FirstW", (wintypes.HANDLE, ctypes.POINTER(ProcessEntry)), wintypes.BOOL),
        ("Process32NextW", (wintypes.HANDLE, ctypes.POINTER(ProcessEntry)), wintypes.BOOL),
        ("OpenEventW", (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR), wintypes.HANDLE),
        ("CloseHandle", (wintypes.HANDLE,), wintypes.BOOL),
    ):
        function = getattr(kernel, name)
        function.argtypes = arguments
        function.restype = result
    return kernel


def process_parents(kernel) -> dict[int, int]:
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise OSError("Impossibile verificare i processi della preparazione.")
    parents = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            parents[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return parents


def is_live_ancestor(parents: dict[int, int], subject: int, candidate: int) -> bool:
    if candidate == subject or candidate not in parents:
        return False
    visited = {subject}
    for _ in range(128):
        subject = parents.get(subject, 0)
        if not subject or subject in visited:
            return False
        if subject == candidate:
            return True
        visited.add(subject)
    return False


def authorized(token: str, parent_pid: int, *, kernel=None, parents=None) -> bool:
    match = re.fullmatch(r"([1-9][0-9]{0,9}):([a-f0-9]{32})", token)
    if not match or not 1 <= parent_pid <= 0xFFFFFFFF or int(match[1]) > 0xFFFFFFFF:
        return False
    kernel = kernel if kernel is not None else _kernel()
    parents = process_parents(kernel) if parents is None else parents
    # Never accept a caller-selected process: only the actual direct parent may
    # ask whether its own inherited lease belongs to a living ancestor.
    if parents.get(os.getpid()) != parent_pid:
        return False
    if not is_live_ancestor(parents, parent_pid, int(match[1])):
        return False
    event = kernel.OpenEventW(0x00100000, False,
                             "Local\\NIPAT-Desktop-SetupLease-" + match[2])
    if not event:
        return False
    kernel.CloseHandle(event)
    return True


def main() -> int:
    if sys.platform != "win32" or len(sys.argv) != 2 or not sys.argv[1].isdigit():
        return 2
    try:
        return 0 if authorized(os.environ.get("NIPAT_SETUP_ACTIVITY_TOKEN", ""),
                               int(sys.argv[1])) else 1
    except (OSError, ValueError) as error:
        print(f"Coordinamento NIPAT non verificabile: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
