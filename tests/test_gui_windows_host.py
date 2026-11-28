"""Portable ABI and policy tests; the native CI smoke exercises Windows itself."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pytest

from newpat.desktop import windows_host as host

URL = "http://127.0.0.1:45678/a-random-capability/web/index.html"


@pytest.mark.parametrize("target", [
    URL, URL + "#archive", URL + "?lang=en",
    "http://127.0.0.1:45678/a-random-capability/resources/file-token",
])
def test_capability_navigation_allowed(target):
    assert host.allowed_navigation(URL, target)


@pytest.mark.parametrize("target", [
    "https://example.org/", "file:///C:/Users/test/file.txt", "javascript:alert(1)",
    "http://127.0.0.1:45679/a-random-capability/web/index.html",
    "http://localhost:45678/a-random-capability/web/index.html",
    "http://127.0.0.1:45678/another-capability/web/index.html",
    "http://127.0.0.1:45678/a-random-capabilityX/web/index.html",
    "http://127.0.0.1:45678/a-random-capability/../private",
    "http://127.0.0.1:45678/a-random-capability/%2e%2e/private",
    "http://127.0.0.1:45678/a-random-capability/%252e%252e/private",
    "http://127.0.0.1:45678/a-random-capability/%5cprivate",
    "http://user@127.0.0.1:45678/a-random-capability/web/index.html",
    "http://127.0.0.1:bad/a-random-capability/web/index.html",
])
def test_external_and_capability_escaping_navigation_blocked(target):
    assert not host.allowed_navigation(URL, target)


def test_fixed_width_windows_abi_on_64_bit_host():
    assert C.sizeof(host.GUID) == 16
    assert C.sizeof(host.RECT) == 16
    assert C.sizeof(host.POINT) == 8
    if C.sizeof(host.PTR) == 8:
        assert C.sizeof(host.MSG) == 48
        assert C.sizeof(host.WNDCLASSEXW) == 80
    expected = uuid.UUID("4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d").bytes_le
    assert bytes(host.GUID.from_string("4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d")) == expected


def test_com_callback_query_interface_lifetime_and_exception_boundary():
    calls, errors = [], []
    iid = "4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d"
    callback = host._Callback(iid, (host.HRESULT, host.PTR),
                              lambda result, pointer: calls.append((result, pointer)), errors.append)
    output = host.PTR()
    requested = host.GUID.from_string(iid)
    assert host._call(callback.pointer, 0, (C.POINTER(host.GUID), C.POINTER(host.PTR)),
                      C.byref(requested), C.byref(output)) == 0
    assert output.value == callback.pointer.value
    assert host._call(output, 3, (host.HRESULT, host.PTR), 0, host.PTR(42)) == 0
    assert calls == [(0, 42)]
    unsupported = host.GUID.from_string("00000000-0000-0000-0000-000000000001")
    assert host._call(callback.pointer, 0, (C.POINTER(host.GUID), C.POINTER(host.PTR)),
                      C.byref(unsupported), C.byref(output)) == host.E_NOINTERFACE
    assert output.value is None
    host._release(callback.pointer)
    callback.release_owner()
    assert callback.pointer.value not in host._COM_ROOTS
    failure = host._Callback(iid, (), lambda: (_ for _ in ()).throw(ValueError("failure")), errors.append)
    assert host._call(failure.pointer, 3) == host.E_FAIL
    assert isinstance(errors[-1], ValueError)
    failure.release_owner()


def test_dependency_integrity_and_missing_manifest(tmp_path):
    binary = tmp_path / "x64" / "WebView2Loader.dll"
    binary.parent.mkdir()
    binary.write_bytes(b"official bytes fixture")
    manifest = tmp_path / "dependencies.json"
    manifest.write_text(json.dumps({"files": [{"path": "x64/WebView2Loader.dll",
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}]}))
    host.verify_dependency(binary)
    binary.write_bytes(b"altered")
    with pytest.raises(host.NativeHostError, match="alterato"):
        host.verify_dependency(binary)
    manifest.unlink()
    with pytest.raises(host.NativeHostError, match="Manifest"):
        host.verify_dependency(binary)


def test_dialog_filters_from_frontend():
    assert host.normalize_filters([{"name": "BAM", "extensions": ["bam", ".bai"]}]) == [
        ("BAM", "*.bam;*.bai")]
    assert host.normalize_filters([("FASTA", "*.fa;*.fasta"), "*.*"]) == [
        ("FASTA", "*.fa;*.fasta"), ("*.*", "*.*")]
    with pytest.raises(ValueError):
        host.normalize_filters([("Invalid\0label", "*.bam")])


def test_no_external_browser_fallback_and_clear_unsupported_platform():
    if sys.platform != "win32":
        with pytest.raises(host.NativeHostError, match="Windows"):
            host.run_window(URL)
    assert host.request_close() is False
    with pytest.raises(host.NativeHostError, match="non è aperta"):
        host.pick_files()


def test_packaged_native_dependencies_have_matching_hashes():
    folder = Path(host.__file__).parent / "native" / "windows" / "x64"
    if not folder.exists():
        pytest.skip("Native components added by distribution build")
    for name in ["WebView2Loader.dll", "MicrosoftEdgeWebview2Setup.exe"]:
        host.verify_dependency(folder / name)


def test_native_screenshot_png_encodes_bgra_pixels_and_checks_dimensions():
    import struct
    import zlib
    # Two source pixels: opaque red then blue (GDI alpha is not meaningful).
    png = host.encode_bgra_png(b"\0\0\xff\0\xff\0\0\0", 2, 1)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    offset, chunks = 8, {}
    while offset < len(png):
        length = struct.unpack_from(">I", png, offset)[0]
        kind = png[offset+4:offset+8]
        data = png[offset+8:offset+8+length]
        assert zlib.crc32(kind+data) == struct.unpack_from(">I", png, offset+8+length)[0]
        chunks[kind] = data
        offset += 12 + length
    assert struct.unpack_from(">II", chunks[b"IHDR"])[0:2] == (2, 1)
    assert zlib.decompress(chunks[b"IDAT"]) == b"\0\xff\0\0\xff\0\0\xff\xff"
    with pytest.raises(ValueError):
        host.encode_bgra_png(b"", 1, 1)
