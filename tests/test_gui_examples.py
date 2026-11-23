"""The packaged offline example can be saved from the native desktop dialog."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nipat.errors import ValidationError
from nipat.gui.app import DesktopApplication
from nipat.gui.examples import ARCHIVE_NAME, save_example_data


PROJECT = Path(__file__).resolve().parents[1]


def test_native_dialog_offline_save_and_cancel(tmp_path):
    host = Mock()
    host.pick_directory.side_effect = [None, tmp_path]
    layout = SimpleNamespace(project_dir=PROJECT)
    app = DesktopApplication(host=host, service=SimpleNamespace(base_layout=layout))
    try:
        assert app.call("examples.save", {"language": "en"}) == {"cancelled": True}
        assert not any(tmp_path.iterdir())
        result = app.call("examples.save", {"language": "it"})
        assert result == {"path": str(tmp_path / "synthetic-trio")}
        copied = tmp_path / "synthetic-trio"
        entries = (copied / "SHA256SUMS").read_text(encoding="ascii").splitlines()
        for line in entries:
            expected, relative = line.split("  ", 1)
            assert hashlib.sha256((copied / relative).read_bytes()).hexdigest() == expected
        assert (copied / "alignments/mother.bam.bai").is_file()
        with pytest.raises(ValidationError):
            app.call("examples.save", {"path": str(tmp_path)})
        assert host.pick_directory.call_count == 2
    finally:
        app.server.close()


def test_existing_folder_and_concurrent_export_preserve_user_files(tmp_path):
    def export():
        try:
            return save_example_data(PROJECT, tmp_path, "en")
        except ValidationError as exc:
            return str(exc)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: export(), range(2)))
    target = tmp_path / "synthetic-trio"
    assert outcomes.count(target) == 1
    assert any("already exists" in str(outcome) for outcome in outcomes)
    user_file = target / "README.md"
    user_file.write_text("user notes")
    with pytest.raises(ValidationError, match="esiste già"):
        save_example_data(PROJECT, tmp_path, "it")
    assert user_file.read_text() == "user notes"


def test_corrupt_distribution_does_not_create_a_partial_export(tmp_path):
    project = tmp_path / "installation"
    examples = project / "examples"
    examples.mkdir(parents=True)
    archive = examples / ARCHIVE_NAME
    archive.write_bytes(b"incorrect download")
    archive.with_suffix(".zip.sha256").write_bytes((PROJECT / "examples" / (ARCHIVE_NAME + ".sha256")).read_bytes())
    with pytest.raises(ValidationError, match="verified"):
        save_example_data(project, tmp_path, "en")
    assert not (tmp_path / "synthetic-trio").exists()


def test_io_failure_removes_only_files_of_this_export(tmp_path, monkeypatch):
    def fail(source, destination):
        destination.write(b"partial")
        (tmp_path / "synthetic-trio" / "independent.txt").write_text("mine")
        raise OSError("disk full")
    monkeypatch.setattr("nipat.gui.examples.shutil.copyfileobj", fail)
    with pytest.raises(ValidationError, match="disk full"):
        save_example_data(PROJECT, tmp_path, "en")
    remaining = list((tmp_path / "synthetic-trio").rglob("*"))
    assert remaining == [tmp_path / "synthetic-trio/independent.txt"]
    assert remaining[0].read_text() == "mine"
