from pathlib import Path
from types import SimpleNamespace
import json
import struct
from unittest.mock import Mock
import zipfile

import pytest

from nipat.gui.app import DesktopApplication
from nipat.errors import ValidationError


class FakeHost:
    destination = None
    selected = []
    accepted = False
    notices = []
    closed = False
    def pick_files(self, *args):
        return self.selected
    def pick_directory(self, *args):
        return self.selected[0] if self.selected else None
    def save_file(self, *args):
        return self.destination
    def confirm(self, *args):
        return self.accepted
    def notify(self, *args):
        self.notices.append(args)
    def request_close(self):
        self.closed = True


@pytest.fixture
def app(tmp_path):
    host = FakeHost()
    class Store:
        def _run(self, run_id):
            return tmp_path / "run"
        def file_path(self, run_id, file_id):
            if (run_id, file_id) != ("run", "file"):
                raise ValueError("Unknown file")
            return tmp_path / "run" / "original.tsv"
        def export_paths(self, run_id):
            return [(self.file_path(run_id, "file"), "output/original.tsv")]
    service = SimpleNamespace(_results=lambda: Store(), call=lambda *_: {"active": False, "jobs": []})
    (tmp_path / "run").mkdir()
    app = DesktopApplication(host=host, service=service)
    yield app
    app.server.close()


def reference(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_bytes(b">chr1\nACGT\n")
    fai = tmp_path / "reference.fa.fai"
    fai.write_text("chr1\t4\t6\t4\t5\n")
    return fasta, fai


@pytest.mark.parametrize("outcome", [True, False, OSError("No browser available")])
def test_igv_guide_opens_only_its_public_page(app, monkeypatch, outcome):
    open_tab = Mock(side_effect=outcome) if isinstance(outcome, OSError) else Mock(return_value=outcome)
    monkeypatch.setattr("nipat.gui.app.webbrowser.open_new_tab", open_tab)
    assert app.call("igv.about", {}) == {"opened": outcome is True}
    with pytest.raises(ValidationError):
        app.call("igv.about", {"url": app.server.url})
    open_tab.assert_called_once_with("https://igv.org/doc/webapp/")


def test_igv_uses_scoped_urls_and_requires_indexes(app, tmp_path):
    fasta, fai = reference(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_bytes(b"BAM\x01" + struct.pack("<iii", 0, 1, 5) + b"chr1\0" + struct.pack("<i", 4))
    args = {"reference": {"fasta": str(fasta), "index": str(fai)}, "tracks": [{"path": str(bam)}]}
    with pytest.raises(ValidationError, match="BAI"):
        app.prepare_igv(args)
    Path(str(bam) + ".bai").write_bytes(b"BAI\x01" + struct.pack("<iii", 1, 0, 0))
    result = app.prepare_igv(args)
    assert result["locus"] == "all"
    assert result["loadDefaultGenomes"] is False
    for url in [result["reference"]["fastaURL"], result["tracks"][0]["url"], result["tracks"][0]["indexURL"]]:
        assert url.startswith(app.server.base_url + "resources/")
        assert str(tmp_path) not in url
    assert result["tracks"][0]["indexed"] is True


def test_igv_invalid_reference_and_remote_paths(app, tmp_path):
    with pytest.raises(ValidationError, match="locali"):
        app._local_file("https://example.org/sample.bam", "BAM")
    fasta, fai = reference(tmp_path)
    fai.write_text("chr1\tbad\n")
    with pytest.raises(ValidationError, match="FASTA"):
        app.prepare_igv({"reference": {"fasta": str(fasta), "index": str(fai)}})


def test_download_copy_and_zip_preserve_originals(app, tmp_path):
    source = tmp_path / "run" / "original.tsv"
    original = b"value\tNA\r\nzero\t0\r\n"
    source.write_bytes(original)
    app.host.destination = str(tmp_path / "copy.tsv")
    app.export_file({"run_id": "run", "file_id": "file"})
    assert Path(app.host.destination).read_bytes() == original
    app.host.destination = str(tmp_path / "archive.zip")
    result = app.export_run({"run_id": "run"})
    with zipfile.ZipFile(result["path"]) as archive:
        assert archive.read("output/original.tsv") == original
    app.host.destination = str(source)
    with pytest.raises(ValidationError, match="originale"):
        app.export_file({"run_id": "run", "file_id": "file"})
    assert source.read_bytes() == original


def test_export_preserves_sibling_results_and_existing_copy_on_failure(app, tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "original.tsv").write_bytes(b"result")
    sibling = run / "run.json"
    sibling.write_bytes(b'{"status": "succeeded"}')
    app.host.destination = sibling
    with pytest.raises(ValidationError):
        app.export_file({"run_id": "run", "file_id": "file"})
    with pytest.raises(ValidationError):
        app.export_run({"run_id": "run"})
    assert sibling.read_bytes() == b'{"status": "succeeded"}'

    destination = tmp_path / "previous.tsv"
    destination.write_bytes(b"previous")
    app.host.destination = destination
    def incomplete_copy(_source, temporary):
        temporary.write_bytes(b"partial")
        raise OSError("disk full")
    monkeypatch.setattr("nipat.gui.app.shutil.copyfile", incomplete_copy)
    with pytest.raises(OSError):
        app.export_file({"run_id": "run", "file_id": "file"})
    assert destination.read_bytes() == b"previous"
    assert set(tmp_path.iterdir()) == {run, destination}


def test_cancel_dialogs_and_active_close(app, tmp_path):
    (tmp_path / "run" / "original.tsv").write_text("a\tb\n")
    assert app.export_file({"run_id": "run", "file_id": "file"}) == {"cancelled": True}
    assert app.dialog({}) == {"paths": []}
    assert app.on_close() is True
    app.service.call = lambda *_: {"active": True, "jobs": [{"id": "one"}]}
    assert app.on_close() is False
    assert app.call("app.close", {}) == {"closing": True}
    assert app.host.closed


def test_sessions_export_durable_paths_not_capabilities(app, tmp_path, monkeypatch):
    app.host.destination = str(tmp_path / "session.json")
    with pytest.raises(ValidationError, match="temporanei"):
        app.save_igv_session({"session": {"url": app.server.url}})
    session = {"reference": {"fasta": str(tmp_path / "reference.fa")}, "tracks": [], "locus": "chr1"}
    dialog = Mock(return_value=app.host.destination)
    monkeypatch.setattr(app.host, "save_file", dialog)
    app.save_igv_session({"session": session})
    assert dialog.call_args.args[1] == "NewPat_IGV_session.json"
    assert json.loads(Path(app.host.destination).read_text(encoding="utf-8")) == session
