"""Console-free startup must retain diagnostics and its own installation lease."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from newpat import cli
from newpat.desktop import windows_host


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "scripts/windows/gui-launch.py"


def load_launcher():
    spec = importlib.util.spec_from_file_location("newpat_gui_launcher", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gui_launch_logs_streams_and_restores_them(tmp_path, monkeypatch):
    monkeypatch.setenv("NEWPAT_WORKSPACE_DIR", str(tmp_path / "User files & è"))
    original = sys.stdout, sys.stderr

    def launch(args):
        assert args == ["gui"]
        assert sys.stdout is sys.stderr
        print("visible diagnostic in the startup log")
        return 0

    monkeypatch.setattr(cli, "main", launch)
    assert load_launcher().main() == 0
    assert (sys.stdout, sys.stderr) == original
    log = (tmp_path / "User files & è/logs/gui-launch.log").read_text()
    assert "visible diagnostic in the startup log" in log


@pytest.mark.parametrize("exception", [False, True])
def test_startup_failure_is_visible_even_without_a_console(tmp_path, monkeypatch, exception):
    monkeypatch.setenv("NEWPAT_WORKSPACE_DIR", str(tmp_path))
    notices = []
    monkeypatch.setattr(windows_host, "notify", lambda *args: notices.append(args))

    def fail(args):
        if exception:
            raise RuntimeError("fixture startup failure")
        print("installation is currently busy", file=sys.stderr)
        return 1

    monkeypatch.setattr(cli, "main", fail)
    assert load_launcher().main() == 1
    assert len(notices) == 1
    assert str(tmp_path / "logs/gui-launch.log") in notices[0][1]
    log = (tmp_path / "logs/gui-launch.log").read_text()
    assert ("fixture startup failure" if exception else "installation is currently busy") in log


def test_native_window_uses_packaged_newpat_identity_and_icon():
    assert windows_host.APP_USER_MODEL_ID == "NewPat.Desktop"
    icon = windows_host.application_icon()
    assert icon == ROOT / "assets/branding/newpat-icon.ico"
    assert icon.read_bytes().startswith(b"\x00\x00\x01\x00")


@pytest.mark.skipif(sys.platform != "win32", reason="requires real Windows pythonw and process leases")
def test_detached_pythonw_keeps_gui_activity_lease_after_launcher_exits(tmp_path, monkeypatch):
    from newpat.activity import _windows_kernel, windows_activity_path

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    assert pythonw.is_file(), "Windows qualification requires the official windowed interpreter"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    env = dict(os.environ, NEWPAT_PROJECT_DIR=str(ROOT), NEWPAT_WORKSPACE_DIR=str(tmp_path / "User & è"),
               PYTHONPATH=str(ROOT / "src"))
    for name in ("NEWPAT_DATA_DIR", "NEWPAT_RUNS_DIR", "NEWPAT_SETUP_ACTIVITY_TOKEN"):
        env.pop(name, None)
    ready, release, finished = (tmp_path / name for name in ("ready.json", "release", "finished"))
    child = tmp_path / "windowed fixture.py"
    child.write_text(f'''
import ctypes, importlib.util, json, os, time
from pathlib import Path
from newpat.desktop import app, windows_host
ready, release, finished = map(Path, {list(map(str, (ready, release, finished)))!r})
windows_host.notify = lambda *args: ready.with_suffix('.error').write_text(str(args))
def keep_open(*args, **kwargs):
    ready.write_text(json.dumps({{'pid': os.getpid(), 'console': ctypes.windll.kernel32.GetConsoleWindow()}}))
    deadline = time.monotonic() + 30
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return 0
app.main = keep_open
spec = importlib.util.spec_from_file_location('windowed_launcher', {str(LAUNCHER)!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
finished.write_text(str(module.main()))
''', encoding="utf-8")
    # The intermediate launcher exits immediately. The GUI child must own its
    # lease rather than relying on a still-open PowerShell/terminal process.
    starter = "import subprocess; subprocess.Popen(" + repr([str(pythonw), str(child)]) + ", stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"
    subprocess.run([sys.executable, "-c", starter], env=env, check=True, timeout=10,
                   creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "pythonw GUI failed to start; inspect fixture logs"
        assert json.loads(ready.read_text())["console"] == 0
        kernel = _windows_kernel()
        handle = kernel.CreateFileW(str(windows_activity_path()), 0xC0000000, 0, None, 4, 0x80, None)
        assert handle == ctypes.c_void_p(-1).value, "windowed GUI must block an exclusive installation"
    finally:
        release.touch()
        deadline = time.monotonic() + 10
        while not finished.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
    assert finished.read_text() == "0"
    # Activity/session cleanup occurs before the entrypoint reports completion.
    handle = kernel.CreateFileW(str(windows_activity_path()), 0xC0000000, 0, None, 4, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value
    kernel.CloseHandle(handle)
