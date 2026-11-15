import ctypes as C
from concurrent.futures import Future
import queue
import sys

import pytest

from nipat.gui import macos_host as host


def test_apple_block_and_geometry_64_bit_abi():
    assert C.sizeof(host.CGPoint) == 16
    assert C.sizeof(host.CGSize) == 16
    assert C.sizeof(host.CGRect) == 32
    assert C.sizeof(host._BlockLiteral) == 32
    assert C.sizeof(host._BlockDescriptor) == 24
    assert host._BlockLiteral.invoke.offset == 16
    assert host._BlockLiteral.descriptor.offset == 24


def test_navigation_decision_block_receives_policy_and_block_pointer():
    decisions = []
    callback = C.CFUNCTYPE(None, host.PTR, host.NSInteger)(
        lambda pointer, policy: decisions.append((pointer, policy)))
    descriptor = host._BlockDescriptor(0, C.sizeof(host._BlockLiteral), b"v@?q")
    literal = host._BlockLiteral(None, 1 << 28, 0, C.cast(callback, host.PTR), C.pointer(descriptor))
    pointer = C.cast(C.pointer(literal), host.PTR)
    host._invoke_decision(pointer, 0)
    host._invoke_decision(pointer, 1)
    assert decisions == [(pointer.value, 0), (pointer.value, 1)]


def test_filter_extensions_handle_shared_frontend_contract():
    assert host.filter_extensions([{"name": "Alignments", "extensions": ["bam", "cram"]}]) == ["bam", "cram"]
    assert host.filter_extensions([("Reference", "*.fa;*.fasta;*.fa")]) == ["fa", "fasta"]
    assert host.filter_extensions([("All files", "*.*")]) == []
    assert host.filter_extensions(None) == []


def test_unsupported_platform_is_explicit_and_never_opens_browser():
    if sys.platform != "darwin":
        with pytest.raises(host.NativeHostError, match="macOS"):
            host.run_window("http://127.0.0.1:1234/token/web/index.html")
    assert host.request_close() is False
    with pytest.raises(host.NativeHostError, match="non è aperta"):
        host.pick_directory()


def test_close_from_async_callback_wakes_event_loop_and_rejects_queued_calls():
    calls = []
    class Cocoa:
        def cls(self, name):
            assert name == "NSEvent"
            return 201
        def send(self, obj, selector, result=host.PTR, argtypes=(), *args):
            calls.append((obj, selector, argtypes, args))
            return 301 if selector.startswith("otherEventWithType:") else None
    window = host._Window.__new__(host._Window)
    window.closed, window.app, window.cocoa = False, 101, Cocoa()
    window.tasks = queue.Queue()
    pending = Future()
    window.tasks.put((pending, lambda: pytest.fail("A queued operation ran during close")))
    window._will_close(None)
    assert window.closed and window.tasks.empty()
    with pytest.raises(host.NativeHostError, match="chiusa"):
        pending.result()
    assert calls[0][1] == "stop:"
    assert calls[1][1].startswith("otherEventWithType:") and calls[1][3][0] == 13
    assert calls[1][2] == (host.NSUInteger, host.CGPoint, host.NSUInteger, C.c_double,
                           host.NSInteger, host.PTR, C.c_short, host.NSInteger, host.NSInteger)
    assert calls[2] == (101, "postEvent:atStart:", (host.PTR, host.BOOL), (301, False))
    window._will_close(None)
    assert len(calls) == 3
    with pytest.raises(host.NativeHostError, match="chiusa"):
        window.invoke(lambda: None)
