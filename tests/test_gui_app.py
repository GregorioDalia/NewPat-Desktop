from pathlib import Path
from types import SimpleNamespace
import json
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
        def file_path(self, run_id, file_id):
            if (run_id, file_id) != ("run", "file"):
                raise ValueError("Unknown file")
            return tmp_path / "original.tsv"
        def files(self, run_id):
            return [{"id": "file", "relative_path": "output/original.tsv"}]
    service = SimpleNamespace(_results=lambda: Store(), call=lambda *_: {"active": False, "jobs": []})
    app = DesktopApplication(host=host, service=service)
    yield app
    app.server.close()


def reference(tmp_path):
    fasta = tmp_path / "reference.fa"
    fasta.write_text(">chr1\nACGT\n")
    fai = tmp_path / "reference.fa.fai"
    fai.write_text("chr1\t4\t6\t4\t5\n")
    return fasta, fai


def test_igv_uses_scoped_urls_and_requires_indexes(app, tmp_path):
    fasta, fai = reference(tmp_path)
    bam = tmp_path / "sample.bam"
    bam.write_bytes(b"BAM\x01")
    args = {"reference": {"fasta": str(fasta), "index": str(fai)}, "tracks": [{"path": str(bam)}]}
    with pytest.raises(ValidationError, match="BAI"):
        app.prepare_igv(args)
    Path(str(bam) + ".bai").write_bytes(b"BAI\x01")
    result = app.prepare_igv(args)
    assert result["locus"] == "chr1"
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
    source = tmp_path / "original.tsv"
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


def test_cancel_dialogs_and_active_close(app, tmp_path):
    (tmp_path / "original.tsv").write_text("a\tb\n")
    assert app.export_file({"run_id": "run", "file_id": "file"}) == {"cancelled": True}
    assert app.dialog({}) == {"paths": []}
    assert app.on_close() is True
    app.service.call = lambda *_: {"active": True, "jobs": [{"id": "one"}]}
    assert app.on_close() is False
    assert app.call("app.close", {}) == {"closing": True}
    assert app.host.closed


def test_sessions_export_durable_paths_not_capabilities(app, tmp_path):
    app.host.destination = str(tmp_path / "session.json")
    with pytest.raises(ValidationError, match="temporanei"):
        app.save_igv_session({"session": {"url": app.server.url}})
    session = {"reference": {"fasta": str(tmp_path / "reference.fa")}, "tracks": [], "locus": "chr1"}
    app.save_igv_session({"session": session})
    assert json.loads(Path(app.host.destination).read_text(encoding="utf-8")) == session
