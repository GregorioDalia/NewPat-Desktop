"""Prepare WSL using Microsoft's system executables, with scoped UAC prompts.

This module runs as the ordinary user. Only fixed DISM/WSL commands are elevated;
no NIPAT executable, interpreter, script or downloaded command runs as admin.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import locale
import os
from pathlib import Path
import re
import subprocess
import sys


def supports(os64: bool, process64: bool, architecture: str, build: int,
             installation_type: str) -> bool:
    return (os64 and process64 and architecture.upper() == "AMD64"
            and installation_type.lower() == "client" and (build == 19045 or build >= 22000))


def modern_wsl(code: int, text: str | None) -> bool:
    first = next((line for line in (text or "").replace("\0", "").splitlines()
                  if line.strip()), "")
    match = re.search(r"\b[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?\b", first)
    return code == 0 and match is not None and tuple(map(int, match[0].split("."))) >= (1, 0, 0)


def wsl_command(modern: bool, help_text: str) -> list[str] | None:
    help_text = help_text.replace("\0", "")
    web = ["--web-download"] if "--web-download" in help_text else []
    if "--update" in help_text:
        return ["--update", *web]
    if not modern and "--install" in help_text and "--no-distribution" in help_text:
        return ["--install", "--no-distribution", *web]
    return None


def system_directory() -> Path:
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    kernel.GetSystemDirectoryW.restype = wintypes.UINT
    buffer = ctypes.create_unicode_buffer(32768)
    length = kernel.GetSystemDirectoryW(buffer, len(buffer))
    if not length or length >= len(buffer):
        raise ctypes.WinError()
    return Path(buffer.value)


def _allowed_command(executable: str, arguments: list[str]) -> bool:
    if executable == "dism.exe":
        return arguments in [
            ["/Online", "/Enable-Feature", "/FeatureName:" + feature, "/All", "/NoRestart"]
            for feature in ("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform")
        ]
    if executable == "wsl.exe":
        return arguments in [
            ["--update"], ["--update", "--web-download"],
            ["--install", "--no-distribution"],
            ["--install", "--no-distribution", "--web-download"],
        ]
    return False


class ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def run_elevated(executable: str, arguments: list[str]) -> int:
    if not _allowed_command(executable, arguments):
        raise ValueError("Comando elevato non previsto dalla preparazione WSL.")
    directory = system_directory()
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100  # Retain exact child handle; finish shell handoff before returning.
    info.lpVerb = "runas"
    info.lpFile = str(directory / executable)
    info.lpParameters = subprocess.list2cmdline(arguments)
    info.lpDirectory = str(directory)
    info.nShow = 1
    print("NIPAT: autorizzazione Windows per " + executable + " " + info.lpParameters, flush=True)
    ole = ctypes.WinDLL("ole32", use_last_error=True)
    ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole.CoInitializeEx.restype = ctypes.c_long
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    initialized = ole.CoInitializeEx(None, 0x2 | 0x4)
    if initialized not in (0, 1):
        raise OSError("Windows non ha inizializzato il controllo UAC.")
    try:
        if not shell.ShellExecuteExW(ctypes.byref(info)):
            error = ctypes.get_last_error()
            if error == 1223:
                return error
            raise ctypes.WinError(error)
    finally:
        ole.CoUninitialize()
    if not info.hProcess:
        raise OSError("Windows non ha restituito il processo di configurazione.")
    try:
        wait = kernel.WaitForSingleObject(info.hProcess, 30 * 60 * 1000)
        if wait == 258:
            # Servicing may continue inside Windows. Do not terminate DISM while
            # it changes system features; setup reports the bounded timeout.
            return 1460
        if wait != 0:
            raise ctypes.WinError()
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            raise ctypes.WinError()
        return int(code.value)
    finally:
        kernel.CloseHandle(info.hProcess)


def probe(arguments: list[str]) -> tuple[int, str]:
    if arguments not in (["--version"], ["--help"]):
        raise ValueError("Verifica WSL non prevista.")
    completed = subprocess.run([str(system_directory() / "wsl.exe"), *arguments],
                               stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    raw = completed.stdout
    encoding = "utf-16-le" if b"\0" in raw else locale.getpreferredencoding(False)
    return completed.returncode, raw.decode(encoding, errors="replace").replace("\ufeff", "")


def configure(elevate=run_elevated, inspect=probe) -> int:
    reboot = False
    for feature in ("Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform"):
        code = elevate("dism.exe", ["/Online", "/Enable-Feature", "/FeatureName:" + feature,
                                    "/All", "/NoRestart"])
        if code in (3010, 1641):
            reboot = True
        elif code != 0:
            return code
    if reboot:
        return 3010
    code, text = inspect(["--version"])
    _, help_text = inspect(["--help"])
    command = wsl_command(modern_wsl(code, text), help_text)
    if command is None:
        return 50
    code = elevate("wsl.exe", command)
    if code in (3010, 1641):
        return 3010
    if code != 0:
        return code
    code, text = inspect(["--version"])
    if modern_wsl(code, text):
        return 0
    _, help_text = inspect(["--help"])
    if "--install" not in help_text or "--no-distribution" not in help_text:
        return 50
    command = ["--install", "--no-distribution"]
    if "--web-download" in help_text:
        command.append("--web-download")
    code = elevate("wsl.exe", command)
    return 3010 if code == 1641 else code


def main() -> int:
    if len(sys.argv) != 1 or sys.platform != "win32":
        return 87
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion") as key:
            build = int(winreg.QueryValueEx(key, "CurrentBuildNumber")[0])
            installation_type = str(winreg.QueryValueEx(key, "InstallationType")[0])
        architecture = os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")
        process64 = ctypes.sizeof(ctypes.c_void_p) == 8
        if not supports(process64, process64, architecture, build, installation_type):
            return 50
        return configure()
    except subprocess.TimeoutExpired:
        return 1460
    except (OSError, ValueError) as error:
        print(f"Prerequisiti WSL non configurati: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
