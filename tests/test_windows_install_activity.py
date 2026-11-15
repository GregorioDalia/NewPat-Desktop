import os
from unittest.mock import MagicMock

from nipat.windows_install_activity import authorized, is_live_ancestor


def test_lease_requires_actual_parent_live_ancestor_and_named_event():
    kernel = MagicMock()
    kernel.OpenEventW.return_value = 42
    token = "100:" + "a" * 32
    parents = {os.getpid(): 200, 200: 100, 100: 1, 1: 0}
    assert authorized(token, 200, kernel=kernel, parents=parents)
    kernel.OpenEventW.assert_called_once_with(0x00100000, False,
                                            "Local\\NIPAT-Desktop-SetupLease-" + "a" * 32)
    kernel.CloseHandle.assert_called_once_with(42)
    assert not authorized(token, 300, kernel=kernel, parents=parents)
    assert not authorized("200:" + "a" * 32, 200, kernel=kernel, parents=parents)
    kernel.OpenEventW.return_value = 0
    assert not authorized(token, 200, kernel=kernel, parents=parents)


def test_missing_or_reused_ancestor_is_not_authorization():
    kernel = MagicMock()
    kernel.OpenEventW.return_value = 42
    parents = {os.getpid(): 200, 200: 100}
    assert not authorized("100:" + "a" * 32, 200, kernel=kernel, parents=parents)
    parents[100] = 1
    assert not authorized("300:" + "a" * 32, 200, kernel=kernel, parents=parents)
    kernel.OpenEventW.assert_not_called()


def test_invalid_tokens_fail_without_loading_native_apis():
    for token in ("", "x", "0:" + "a" * 32, "4294967296:" + "a" * 32,
                  "1:" + "A" * 32, "1:" + "a" * 31, "1:" + "a" * 32 + "\n"):
        assert not authorized(token, 200)


def test_parent_cycles_and_excessive_depth_fail_closed():
    assert not is_live_ancestor({1: 2, 2: 1, 3: 0}, 1, 3)
    assert not is_live_ancestor({1: 1}, 1, 1)
    parents = {value: value + 1 for value in range(1, 200)}
    parents[200] = 0
    assert not is_live_ancestor(parents, 1, 200)
