import gzip
from hashlib import sha256
from http.client import IncompleteRead
import io
from pathlib import Path
from threading import Event
import time
from types import SimpleNamespace

import pytest

from nipat.errors import ValidationError
from nipat.gui import reference_downloads as downloads


FASTA = b">chrExample\nACGTACGT\nACGTACGT\n"
PACKED = gzip.compress(FASTA, mtime=0)
SOURCE = downloads.ReferenceSource("hg19", len(PACKED), sha256(PACKED).hexdigest(),
                                  len(FASTA), sha256(FASTA).hexdigest(),
                                  sha256(b"chrExample\t16\t12\t8\t9\n").hexdigest())


class Catalog:
    def __init__(self, folder):
        self.path = folder / "references.json"
        self.entries = []

    def register(self, build, fasta):
        assert fasta.read_bytes() == FASTA
        assert Path(str(fasta) + ".fai").read_text().strip() == "chrExample\t16\t12\t8\t9"
        entry = {"id": "example", "build": build, "fasta": str(fasta)}
        self.entries.append(entry)
        return entry


@pytest.fixture
def downloads_manager(tmp_path, monkeypatch):
    catalog = Catalog(tmp_path)
    monkeypatch.setitem(downloads.SOURCES, "grch37", SOURCE)
    monkeypatch.setattr(downloads, "urlopen", lambda url, timeout: io.BytesIO(PACKED))
    manager = downloads.ReferenceDownloads(lambda language: catalog)
    yield manager, catalog
    manager.close()


def wait_for(manager, status):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = manager.call("status", {"build": "grch37"})
        if state["status"] not in downloads.ACTIVE:
            assert state["status"] == status, state
            return state
        time.sleep(0.01)
    raise AssertionError(f"Download did not reach {status}")


def test_download_publishes_verified_fasta_index_and_recovers_cached_result(downloads_manager, monkeypatch):
    manager, catalog = downloads_manager
    assert manager.call("status", {"build": "grch37"})["status"] == "idle"
    manager.call("start", {"build": "grch37", "language": "en"})
    done = wait_for(manager, "ready")
    assert done["entry"] == catalog.entries[0]
    assert done["received_bytes"] == done["total_bytes"] == len(PACKED)
    folder = Path(done["entry"]["fasta"]).parent
    assert {p.name for p in folder.iterdir() if not p.name.endswith(".lock")} == {"hg19.fa", "hg19.fa.fai"}
    assert not (folder.parent / "hg19.partial").exists()

    monkeypatch.setattr(downloads, "urlopen", lambda *a, **k: pytest.fail("Unexpected network access"))
    recovered = downloads.ReferenceDownloads(lambda language: catalog)
    recovered.call("start", {"build": "grch37"})
    assert wait_for(recovered, "ready")["entry"] == done["entry"]


@pytest.mark.parametrize("payload", [PACKED[:-3], PACKED[:-1] + b"!", PACKED + b"!", b""])
def test_corrupt_and_truncated_downloads_do_not_publish(downloads_manager, monkeypatch, payload):
    manager, catalog = downloads_manager
    monkeypatch.setattr(downloads, "urlopen", lambda *a, **kw: io.BytesIO(payload))
    manager.call("start", {"build": "grch37"})
    assert wait_for(manager, "failed")["entry"] is None
    assert not catalog.entries
    root = catalog.path.parent / "reference-genomes"
    assert not any(p.is_dir() for p in root.iterdir())


def test_cancellation_cleans_private_staging_and_retry_is_possible(downloads_manager, monkeypatch):
    manager, catalog = downloads_manager
    reading, unblock = Event(), Event()
    calls = []

    class SlowStream(io.BytesIO):
        def read(self, n):
            reading.set()
            assert unblock.wait(5)
            return super().read(n)

    def open_slow(*args, **kwargs):
        calls.append(1)
        return SlowStream(PACKED)
    monkeypatch.setattr(downloads, "urlopen", open_slow)
    try:
        manager.call("start", {"build": "grch37"})
        assert reading.wait(5)
        for _ in range(2):
            assert manager.call("start", {"build": "grch37"})["status"] == "downloading"
        manager.call("cancel", {"build": "grch37"})
    finally:
        unblock.set()
    wait_for(manager, "cancelled")
    assert calls == [1] and not catalog.entries
    manager.call("start", {"build": "grch37"})
    assert wait_for(manager, "ready")["entry"]
    assert len(calls) == 2


def test_disk_check_and_http_errors_are_reported(downloads_manager, monkeypatch):
    manager, catalog = downloads_manager
    monkeypatch.setattr(downloads.shutil, "disk_usage", lambda path: SimpleNamespace(free=0))
    manager.call("start", {"build": "grch37", "language": "en"})
    assert "disk space" in wait_for(manager, "failed")["error"]

    def interrupted(*args, **kwargs):
        raise IncompleteRead(b"", 123)
    monkeypatch.setattr(downloads.shutil, "disk_usage", lambda path: SimpleNamespace(free=10**10))
    monkeypatch.setattr(downloads, "urlopen", interrupted)
    manager.call("start", {"build": "grch37", "language": "en"})
    assert wait_for(manager, "failed")["error"] and not catalog.entries


def test_rpc_accepts_only_known_builds_and_never_a_supplied_url(downloads_manager):
    manager, _ = downloads_manager
    for params in ({"build": "custom"}, {"build": []}, {"build": "grch38", "url": "https://invalid.test/"}):
        with pytest.raises(ValidationError):
            manager.call("start", params)


def test_recovery_keeps_an_altered_installed_file_and_gives_a_repair_path(downloads_manager):
    manager, catalog = downloads_manager
    manager.call("start", {"build": "grch37"})
    fasta = Path(wait_for(manager, "ready")["entry"]["fasta"])
    fasta.write_bytes(b">my_own\nAAAA\n")
    manager.call("start", {"build": "grch37", "language": "en"})
    failed = wait_for(manager, "failed")
    assert "Move" in failed["error"] and str(fasta.parent) in failed["error"]
    assert fasta.read_bytes() == b">my_own\nAAAA\n" and len(catalog.entries) == 1


def test_desktop_rpc_calls_use_the_catalog_and_local_cache(downloads_manager):
    from nipat.gui.app import DesktopApplication

    _, catalog = downloads_manager
    app = DesktopApplication(host=object(), service=SimpleNamespace(reference_catalog=lambda lang: catalog))
    params = {"build": "grch37", "language": "en"}
    assert app.call("references.download_status", params)["status"] == "idle"
    assert app.call("references.download_cancel", params)["status"] == "idle"
    app.call("references.download", params)
    assert wait_for(app.reference_downloads, "ready")["entry"] == catalog.entries[0]


def test_bad_decompressed_hash_does_not_publish_a_verified_gzip(downloads_manager, monkeypatch):
    from dataclasses import replace

    manager, catalog = downloads_manager
    monkeypatch.setitem(downloads.SOURCES, "grch37", replace(SOURCE, fasta_sha256="0" * 64))
    manager.call("start", {"build": "grch37"})
    assert "SHA-256" in wait_for(manager, "failed")["error"]
    assert not (catalog.path.parent / "reference-genomes" / "hg19").exists()


def test_changed_cached_index_is_detected_before_reregistration(downloads_manager):
    manager, catalog = downloads_manager
    manager.call("start", {"build": "grch37"})
    index = Path(wait_for(manager, "ready")["entry"]["fasta"] + ".fai")
    index.write_bytes(b"chrOther\t16\t12\t8\t9\n")
    manager.call("start", {"build": "grch37", "language": "en"})
    assert "Move" in wait_for(manager, "failed")["error"]
    assert len(catalog.entries) == 1


def test_close_during_indexing_leaves_no_partial_bundle(downloads_manager, monkeypatch):
    from nipat.gui import references

    manager, catalog = downloads_manager
    entered, unblock = Event(), Event()

    def index(_fasta, *, check_cancel, progress, language):
        entered.set()
        assert unblock.wait(5)
        check_cancel()
        raise AssertionError("Indexing continued after closure")
    monkeypatch.setattr(references, "build_fasta_index", index)
    try:
        manager.call("start", {"build": "grch37"})
        assert entered.wait(5)
        state = manager.call("status", {"build": "grch37"})
        assert state["status"] == "indexing" and state["phase_total_bytes"] == len(FASTA)
        manager.close()
    finally:
        unblock.set()
    wait_for(manager, "cancelled")
    assert not catalog.entries and not any(
        p.is_dir() for p in (catalog.path.parent / "reference-genomes").iterdir()
    )
