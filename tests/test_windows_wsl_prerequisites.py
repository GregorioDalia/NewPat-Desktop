from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nipat.windows_wsl_prerequisites import (
    _allowed_command, configure, modern_wsl, run_elevated, supports, wsl_command,
)


@pytest.mark.parametrize("build,kind,expected", [
    (19045, "Client", True), (22000, "Client", True), (26100, "Client", True),
    (19044, "Client", False), (20348, "Client", False),
    (20348, "Server", False), (26100, "Server Core", False),
])
def test_supported_windows(build, kind, expected):
    assert supports(True, True, "AMD64", build, kind) == expected


@pytest.mark.parametrize("os64,process64,architecture", [
    (False, False, "x86"), (True, False, "AMD64"), (True, True, "ARM64"),
])
def test_unsupported_architecture(os64, process64, architecture):
    assert not supports(os64, process64, architecture, 26100, "Client")


@pytest.mark.parametrize("code,text,expected", [
    (0, "WSL version: 2.6.1.0", True), (0, "Versione WSL: 1.0.0", True),
    (0, "\nVersion WSL : 2.4.13.0\nVersion du noyau : 5.15.0", True),
    (0, "WSL version: 0.67.6.0", False), (1, "WSL version: 2.6.1.0", False),
    (0, "", False), (0, None, False),
    (0, "Uso: wsl.exe --help\nWindows: 10.0.26100", False),
])
def test_localized_readiness(code, text, expected):
    assert modern_wsl(code, text) == expected


def test_only_distribution_free_install_or_update_commands_are_selected():
    assert wsl_command(True, "--update --web-download") == ["--update", "--web-download"]
    assert wsl_command(False, "--update") == ["--update"]
    assert wsl_command(False, "--install --no-distribution --web-download") == [
        "--install", "--no-distribution", "--web-download"]
    assert wsl_command(False, "--install") is None
    assert wsl_command(True, "--install --no-distribution") is None
    for executable, arguments in (("cmd.exe", ["/c", "echo x"]),
                                  ("wsl.exe", ["--install"]),
                                  ("wsl.exe", ["--import", "distro"]),
                                  ("dism.exe", ["/Online", "/Enable-Feature", "/FeatureName:Other"])):
        assert not _allowed_command(executable, arguments)
        with pytest.raises(ValueError):
            run_elevated(executable, arguments)


def test_windows_feature_reboot_delays_wsl_install_until_resume():
    elevate = Mock(side_effect=[3010, 0])
    inspect = Mock()
    assert configure(elevate, inspect) == 3010
    assert [call.args[1][2] for call in elevate.call_args_list] == [
        "/FeatureName:Microsoft-Windows-Subsystem-Linux", "/FeatureName:VirtualMachinePlatform"]
    inspect.assert_not_called()


@pytest.mark.parametrize("failure", [1223, 1460, 5])
def test_elevation_cancel_timeout_or_failure_stops_setup(failure):
    elevate = Mock(return_value=failure)
    inspect = Mock()
    assert configure(elevate, inspect) == failure
    assert elevate.call_count == 1
    inspect.assert_not_called()


def test_kernel_only_update_falls_back_to_explicit_distribution_free_package():
    elevate = Mock(return_value=0)
    inspect = Mock(side_effect=[(1, ""), (0, "--update --web-download"),
                                (1, "legacy"), (0, "--install --no-distribution --web-download")])
    assert configure(elevate, inspect) == 0
    assert elevate.call_args_list[-1].args == ("wsl.exe", ["--install", "--no-distribution", "--web-download"])
    assert all(_allowed_command(*call.args) for call in elevate.call_args_list)


def test_legacy_wsl_never_installs_an_unrequested_distribution():
    elevate = Mock(return_value=0)
    inspect = Mock(side_effect=[(1, ""), (0, "--install")])
    assert configure(elevate, inspect) == 50
    assert elevate.call_count == 2


@pytest.mark.parametrize("code", [3010, 1641])
def test_wsl_restart_exit_codes_are_preserved(code):
    elevate = Mock(side_effect=[0, 0, code])
    inspect = Mock(side_effect=[(0, "WSL version: 2.6.0"), (0, "--update")])
    assert configure(elevate, inspect) == 3010


def test_elevation_runs_only_system_binary_and_closes_exact_process_handle_on_timeout():
    shell, kernel, ole = Mock(), Mock(), Mock()
    ole.CoInitializeEx.return_value = 0
    kernel.WaitForSingleObject.return_value = 258
    calls = []

    def start(pointer):
        info = pointer._obj
        calls.append((info.lpVerb, info.lpFile, info.lpParameters))
        info.hProcess = 88
        return True

    shell.ShellExecuteExW.side_effect = start
    libraries = {"shell32": shell, "kernel32": kernel, "ole32": ole}
    with patch("nipat.windows_wsl_prerequisites.system_directory", return_value=Path("C:/Windows/System32")), \
            patch("ctypes.WinDLL", create=True, side_effect=lambda name, **_: libraries[name]):
        assert run_elevated("wsl.exe", ["--update", "--web-download"]) == 1460
    assert calls == [("runas", str(Path("C:/Windows/System32/wsl.exe")), "--update --web-download")]
    kernel.CloseHandle.assert_called_once_with(88)
    ole.CoUninitialize.assert_called_once_with()
    kernel.GetExitCodeProcess.assert_not_called()


def test_cancelled_uac_is_reported_without_waiting_or_running_more_commands():
    shell, kernel, ole = Mock(), Mock(), Mock()
    ole.CoInitializeEx.return_value = 0
    shell.ShellExecuteExW.return_value = False
    libraries = {"shell32": shell, "kernel32": kernel, "ole32": ole}
    with patch("nipat.windows_wsl_prerequisites.system_directory", return_value=Path("C:/Windows/System32")), \
            patch("ctypes.WinDLL", create=True, side_effect=lambda name, **_: libraries[name]), \
            patch("ctypes.get_last_error", create=True, return_value=1223):
        assert run_elevated("wsl.exe", ["--update"]) == 1223
    kernel.WaitForSingleObject.assert_not_called()
    ole.CoUninitialize.assert_called_once_with()
