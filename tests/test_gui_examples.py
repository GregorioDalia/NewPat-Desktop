"""The packaged offline example can be saved from the native desktop dialog."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from newpat.errors import ValidationError
from newpat.desktop.app import DesktopApplication
from newpat.desktop.examples import ARCHIVE_NAME, save_example_data


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
    monkeypatch.setattr("newpat.desktop.examples.shutil.copyfileobj", fail)
    with pytest.raises(ValidationError, match="disk full"):
        save_example_data(PROJECT, tmp_path, "en")
    remaining = list((tmp_path / "synthetic-trio").rglob("*"))
    assert remaining == [tmp_path / "synthetic-trio/independent.txt"]
    assert remaining[0].read_text() == "mine"


def test_demo_validates_with_factory_settings_even_with_personal_preferences(tmp_path):
    from newpat.experiments.options import ExecutionOptions
    from newpat.desktop.service import GuiService
    from newpat.paths import ProjectLayout
    from newpat.preferences import Preferences, PreferencesStore
    from newpat.scientific_options import effective_config

    layout = ProjectLayout(PROJECT, tmp_path, tmp_path / "data", tmp_path / "runs", PROJECT / "compose.yaml")
    store = PreferencesStore(tmp_path / "preferences.json")
    preferences = Preferences(scientific_settings={"dnp-call": {"max_depth": 2222}},
                              execution={"max_workers": 1, "execution_mode": "serial"})
    store.save(preferences)
    app = DesktopApplication(host=Mock(), service=GuiService(layout, preferences_store=store))
    try:
        draft = app.call("examples.demo", {"language": "en"})["draft"]
        assert draft["name"] == "DNP and SNP demo"
        assert [row["id"] for row in draft["samples"]] == ["mother", "father", "child"]
        preview = app.call("plan.preview", {"draft": draft})
        assert [step["workflow"] for step in preview["steps"]] == ["dnp-call", "snp-call", "snp-call", "snp-call"]
        assert preview["effective_settings"] == effective_config({})
        assert preview["execution"] == ExecutionOptions().as_dict()
        assert store.load().scientific_settings == preferences.scientific_settings
        assert store.load().execution == preferences.execution
        assert not app.host.method_calls
        assert not layout.runs_dir.exists()
        with pytest.raises(ValidationError):
            app.call("examples.demo", {"path": str(tmp_path)})
    finally:
        app.server.close()


def test_demo_reuses_intact_inputs_and_preserves_altered_copies(tmp_path):
    from newpat.desktop.examples import demo_draft

    layout = SimpleNamespace(project_dir=PROJECT, workspace_dir=tmp_path)
    with ThreadPoolExecutor(max_workers=4) as pool:
        drafts = list(pool.map(lambda _: demo_draft(layout, "it"), range(4)))
    assert all(draft == drafts[0] for draft in drafts)
    assert drafts[0]["name"] == "Demo DNP e SNP"
    bam = Path(drafts[0]["samples"][0]["path"])
    bundled = (PROJECT / "examples/synthetic-trio/alignments/mother.bam").read_bytes()
    assert bam.read_bytes() == bundled
    bam.write_bytes(b"x" * len(bundled))
    replacement = Path(demo_draft(layout, "it")["samples"][0]["path"])
    assert replacement.parent != bam.parent and replacement.read_bytes() == bundled
    assert bam.read_bytes() == b"x" * len(bundled)
    assert Path(demo_draft(layout, "it")["samples"][0]["path"]) == replacement


def test_demo_refuses_damaged_distribution_even_when_previous_inputs_exist(tmp_path):
    from newpat.desktop.examples import demo_draft

    layout = SimpleNamespace(project_dir=PROJECT, workspace_dir=tmp_path)
    draft = demo_draft(layout, "it")
    installation = tmp_path / "installation" / "examples"
    installation.mkdir(parents=True)
    (installation / ARCHIVE_NAME).write_bytes(b"corrupt")
    (installation / (ARCHIVE_NAME + ".sha256")).write_bytes((PROJECT / "examples" / (ARCHIVE_NAME + ".sha256")).read_bytes())
    with pytest.raises(ValidationError, match="verified"):
        demo_draft(SimpleNamespace(project_dir=installation.parent, workspace_dir=tmp_path), "en")
    assert Path(draft["reference"]).is_file()
