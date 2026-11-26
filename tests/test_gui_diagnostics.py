"""Support exports are useful after failure without copying genomic datasets."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import zipfile
import subprocess

import pytest

from nipat.errors import ValidationError
from nipat.gui.app import DesktopApplication
from nipat.gui import diagnostics
from nipat.gui.results import ResultsStore


@pytest.fixture
def layout(tmp_path):
    root = tmp_path / "workspace"
    value = SimpleNamespace(workspace_dir=root, project_dir=tmp_path / "app",
                            data_dir=root / "data", runs_dir=root / "runs")
    for path in (root, value.project_dir, value.data_dir, value.runs_dir):
        path.mkdir(parents=True, exist_ok=True)
    return value


def put(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())
    return path


def read_bundle(path):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name) for name in archive.namelist()}


def test_global_bundle_contains_setup_and_gui_errors_without_an_experiment(layout, tmp_path):
    put(layout.workspace_dir, "logs/gui.log", "IGV reference mismatch\n")
    put(layout.workspace_dir, ".runtime/macos/setup.log", "App mount unavailable\n")
    put(layout.workspace_dir, ".runtime/macos/runtime.json", '{"phase":"ready"}')
    put(layout.data_dir, "private.bam", b"PRIVATE GENOMIC INPUT")
    put(layout.data_dir, "reference.fa", b">private\nACGT")
    put(layout.workspace_dir, "logs/private.txt", "UNRELATED SECRET")
    result = diagnostics.write_bundle(tmp_path / "support.zip", layout,
                                     resources={"status": "unavailable", "error": "VM not ready"})
    content = read_bundle(result["path"])
    manifest = json.loads(content["diagnostics.json"])
    assert manifest["product"] == "NewPat"
    assert manifest["experiment"] is None
    assert manifest["resources"]["error"] == "VM not ready"
    assert content["application/logs/gui.log"] == b"IGV reference mismatch\n"
    assert content["application/.runtime/macos/setup.log"] == b"App mount unavailable\n"
    assert b"PRIVATE GENOMIC INPUT" not in b"".join(content.values())
    assert b"UNRELATED SECRET" not in b"".join(content.values())
    assert not any(name.endswith((".bam", ".fa", ".tsv")) for name in content)


def test_run_export_only_copies_allowlisted_metadata_and_logs(layout, tmp_path):
    run = layout.runs_dir / "run-one"
    put(run, "run.json", '{"status":"failed","workflow":"analysis"}')
    put(run, "execution.log", "Computation failed\n")
    put(run, "performance/engine/summary.json", '{"status":"complete","sample_count":5}')
    put(run, "performance/engine/samples.jsonl", "OMIT DETAILED SAMPLING")
    put(run, "output/workflow/workflow-state.json", '{"status":"failed","snp_summary":{"clinical":"DO NOT EXPORT"}}')
    put(run, "output/workflow/steps/dnp/command.log", "DNP error\n")
    put(run, "output/workflow/steps/dnp/work/input-validation.json", '{"status":"validated"}')
    for prefix in ("work/", "output/workflow/steps/dnp/work/"):
        put(run, prefix + "dnp-block-progress.json", '{"completed_groups":2,"planned_groups":5}')
    put(run, "output/workflow/steps/dnp/output/genotypes.tsv", "PRIVATE GENOTYPES")
    put(run, "work/pileup.txt", "PRIVATE READS")
    result = diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={}, run_dir=run)
    content = read_bundle(result["path"])
    assert content["experiment/output/workflow/steps/dnp/command.log"] == b"DNP error\n"
    for prefix in ("work/", "output/workflow/steps/dnp/work/"):
        assert json.loads(content["experiment/" + prefix + "dnp-block-progress.json"])["completed_groups"] == 2
    assert "snp_summary" not in json.loads(content["experiment/output/workflow/workflow-state.json"])
    all_bytes = b"".join(content.values())
    for secret in (b"PRIVATE GENOTYPES", b"PRIVATE READS", b"OMIT DETAILED SAMPLING", b"DO NOT EXPORT"):
        assert secret not in all_bytes


def test_large_logs_keep_tail_and_invalid_or_oversized_json_is_reported(layout, tmp_path):
    put(layout.workspace_dir, "logs/gui.log", b"old" + b"x" * diagnostics.MAX_FILE_BYTES + b"LATEST")
    put(layout.workspace_dir, ".runtime/macos/runtime.json", b" " * (diagnostics.MAX_FILE_BYTES + 1))
    result = diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={})
    content = read_bundle(result["path"])
    assert len(content["application/logs/gui.log"]) == diagnostics.MAX_FILE_BYTES
    assert content["application/logs/gui.log"].endswith(b"LATEST")
    records = {x["path"]: x for x in json.loads(content["diagnostics.json"])["files"]}
    assert records["application/logs/gui.log"]["truncated"] is True
    assert records["application/.runtime/macos/runtime.json"]["status"] == "omitted"
    assert result["omitted"] == 1


def test_total_budget_bounds_collected_bytes(layout, tmp_path, monkeypatch):
    put(layout.workspace_dir, "logs/gui.log", "abcdefghij")
    put(layout.workspace_dir, ".runtime/macos/setup.log", "1234567890")
    put(layout.workspace_dir, ".runtime/macos/runtime.json", '{"phase":"ready"}')
    monkeypatch.setattr(diagnostics, "MAX_TOTAL_BYTES", 12)
    content = read_bundle(diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={})["path"])
    assert sum(len(v) for k, v in content.items() if k != "diagnostics.json") <= 12
    assert content["application/.runtime/macos/setup.log"] == b"90"
    assert any(x["status"] == "omitted" for x in json.loads(content["diagnostics.json"])["files"])


def test_external_file_and_directory_links_are_never_exported(layout, tmp_path):
    outside = put(tmp_path, "secret.log", "PRIVATE OUTSIDE")
    logs = layout.workspace_dir / "logs"
    logs.mkdir()
    try:
        (logs / "gui.log").symlink_to(outside)
        (layout.workspace_dir / ".runtime").symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    content = read_bundle(diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={})["path"])
    assert b"PRIVATE OUTSIDE" not in b"".join(content.values())
    records = json.loads(content["diagnostics.json"])["files"]
    assert any(x["path"] == "application/logs/gui.log" and x["status"] == "omitted" for x in records)


def test_export_never_overwrites_source_or_follows_destination_link(layout, tmp_path):
    source = put(layout.data_dir, "keep.zip", b"original")
    with pytest.raises(ValidationError, match="fuori"):
        diagnostics.write_bundle(source, layout, resources={})
    assert source.read_bytes() == b"original"
    with pytest.raises(ValidationError, match=r"\.zip"):
        diagnostics.write_bundle(tmp_path / "keep.bam", layout, resources={})
    linked = tmp_path / "linked.zip"
    try:
        linked.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    with pytest.raises(ValidationError, match="collegamento"):
        diagnostics.write_bundle(linked, layout, resources={})
    assert source.read_bytes() == b"original"


def test_failed_zip_preserves_previous_destination_and_cleans_temporary(layout, tmp_path):
    destination = put(tmp_path, "support.zip", b"previous archive")
    before = set(tmp_path.iterdir())
    with patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            diagnostics.write_bundle(destination, layout, resources={})
    assert destination.read_bytes() == b"previous archive"
    assert set(tmp_path.iterdir()) == before


def test_rpc_exports_after_environment_failure_and_cancellation_is_side_effect_free(layout, tmp_path):
    host = Mock()
    host.save_file.return_value = None
    service = SimpleNamespace(layout=layout, base_layout=layout,
                              resources_get=Mock(side_effect=ValidationError("Lima unavailable")))
    app = DesktopApplication(host=host, service=service)
    try:
        assert app.call("diagnostics.export", {}) == {"cancelled": True}
        service.resources_get.assert_not_called()
        host.save_file.return_value = str(tmp_path / "support.zip")
        result = app.call("diagnostics.export", {})
        manifest = json.loads(read_bundle(result["path"])["diagnostics.json"])
        assert manifest["resources"] == {"status": "unavailable", "error": "Lima unavailable"}
        with pytest.raises(ValidationError):
            app.call("diagnostics.export", {"path": "/arbitrary"})
    finally:
        app.server.close()


def test_native_folder_and_diagnostics_accept_only_registered_run_ids(layout, tmp_path):
    run = layout.runs_dir / "one"
    put(run, "run.json", '{"status":"succeeded"}')
    store = ResultsStore(layout.runs_dir)
    host = Mock()
    host.save_file.return_value = str(tmp_path / "support.zip")
    service = SimpleNamespace(layout=layout, base_layout=layout, _results=lambda: store, resources_get=lambda: {})
    app = DesktopApplication(host=host, service=service)
    try:
        with patch.object(diagnostics, "open_directory") as launch:
            assert app.call("runs.open_directory", {"run_id": "one"}) == {"opened": True}
            launch.assert_called_once_with(run)
            for bad in ("../outside", "/arbitrary", "missing", "one/../one"):
                with pytest.raises((ValueError, ValidationError)):
                    app.call("runs.open_directory", {"run_id": bad})
                with pytest.raises((ValueError, ValidationError)):
                    app.call("diagnostics.export", {"run_id": bad})
            assert launch.call_count == 1
        result = app.call("diagnostics.export", {"run_id": "one"})
        assert "experiment/run.json" in read_bundle(result["path"])
    finally:
        app.server.close()


def test_broken_preferences_still_allow_export_of_application_log(layout, tmp_path):
    put(layout.workspace_dir, "logs/gui.log", "Preferences could not be read")

    class BrokenService:
        def __init__(self, base_layout):
            self.base_layout = base_layout

        @property
        def layout(self):
            raise ValueError("Invalid preferences")

        def resources_get(self):
            raise ValueError("Invalid preferences")

    host = Mock()
    host.save_file.return_value = str(tmp_path / "support.zip")
    app = DesktopApplication(host=host, service=BrokenService(layout))
    try:
        content = read_bundle(app.call("diagnostics.export", {})["path"])
        assert content["application/logs/gui.log"] == b"Preferences could not be read"
        assert json.loads(content["diagnostics.json"])["resources"]["status"] == "unavailable"
    finally:
        app.server.close()


def test_workflow_step_and_file_limits_are_reported(layout, tmp_path, monkeypatch):
    run = layout.runs_dir / "many-steps"
    put(run, "run.json", '{}')
    for index in range(4):
        put(run, f"output/workflow/steps/step-{index}/command.log", "step log")
    monkeypatch.setattr(diagnostics, "MAX_STEPS", 2)
    monkeypatch.setattr(diagnostics, "MAX_FILES", 2)
    result = diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={}, run_dir=run)
    content = read_bundle(result["path"])
    assert len(content) == 3  # manifest plus at most two source files
    assert result["omitted"] == 2  # a limited file and the remaining steps


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs unavailable")
def test_nonregular_log_is_omitted_without_opening_it(layout, tmp_path):
    logs = layout.workspace_dir / "logs"
    logs.mkdir()
    os.mkfifo(logs / "gui.log")
    content = read_bundle(diagnostics.write_bundle(tmp_path / "support.zip", layout, resources={})["path"])
    assert "application/logs/gui.log" not in content
    assert json.loads(content["diagnostics.json"])["files"][0]["status"] == "omitted"


@pytest.mark.parametrize("platform,command", [("darwin", "/usr/bin/open"), ("linux", "xdg-open")])
def test_native_folder_uses_argument_list_and_explains_open_failure(tmp_path, monkeypatch, platform, command):
    folder = tmp_path / "experiment with spaces"
    folder.mkdir()
    monkeypatch.setattr(diagnostics.sys, "platform", platform)
    with patch.object(subprocess, "run") as launch:
        diagnostics.open_directory(folder)
        assert launch.call_args.args == ([command, str(folder)],)
        assert launch.call_args.kwargs.get("shell", False) is False
        launch.side_effect = subprocess.CalledProcessError(1, command)
        with pytest.raises(ValidationError, match="Impossibile aprire"):
            diagnostics.open_directory(folder)
