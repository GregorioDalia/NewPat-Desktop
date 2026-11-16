"""Crash recovery is observational; list removal never deletes scientific files."""
from contextlib import contextmanager, nullcontext
import os
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from unittest.mock import Mock

import pytest

from nipat.errors import ValidationError
from nipat.gui.lifecycle import RunObserver
from nipat.gui.results import ResultsStore
from nipat.gui.service import GuiService
from nipat.paths import ProjectLayout
from nipat.preferences import PreferencesStore
from nipat.resources import _resource_lock


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def recorded(tmp_path):
    root = tmp_path / "runs"
    run = root / "example"
    metadata = {"schema_version": 1, "workflow": "dnp-call", "status": "running",
                "commands": [], "parameters": {}, "source": {}, "run_name": "testgrafico1"}
    write(run / "run.json", metadata)
    os.utime(run / "run.json", (time.time() - 10,) * 2)
    (run / "output").mkdir()
    (run / "output" / "result.tsv").write_text("original\n")
    project = tmp_path / "project"
    project.mkdir()
    layout = ProjectLayout(project, tmp_path, tmp_path / "data", root, project / "compose.yaml")
    return run, metadata, layout


def observer(recorded, report=None, jobs=None, **kwargs):
    _, _, layout = recorded
    jobs = jobs or SimpleNamespace(active=lambda: {"active": False, "jobs": []})
    return RunObserver(lambda: layout, jobs, runner_factory=lambda _: object(),
                       reconcile=Mock(return_value=report or {"backend_matches": True, "containers": []}),
                       guard=kwargs.pop("guard", nullcontext), **kwargs)


def test_confirmed_abandonment_never_rewrites_run_or_promotes_step_success(recorded):
    run, metadata, _ = recorded
    write(run / "output/workflow/workflow-state.json", {"schema_version": 1, "status": "succeeded", "steps": []})
    original = (run / "run.json").read_bytes()
    observation = observer(recorded).inspect(run, metadata)
    assert observation == {"status": "interrupted", "recorded_status": "running",
                           "status_reason": "abandoned", "can_remove": True}
    assert (run / "run.json").read_bytes() == original


@pytest.mark.parametrize("report,expected", [
    ({"backend_matches": False, "containers": []}, "unknown"),
    ({"backend_matches": True, "containers": [{"state": "unavailable"}]}, "unknown"),
    ({"backend_matches": True, "containers": [{"state": "identity_mismatch"}]}, "unknown"),
    ({"backend_matches": True, "containers": [{"state": "running", "owned": True}]}, "running"),
    ({"backend_matches": True, "containers": [{"state": "running", "owned": False}]}, "running"),
    ({"backend_matches": True, "containers": [{"state": "unexpected"}]}, "unknown"),
])
def test_inconclusive_or_live_runtime_never_allows_removal(recorded, report, expected):
    run, metadata, _ = recorded
    result = observer(recorded, report).inspect(run, metadata)
    assert result["status"] == expected and result["can_remove"] is False


def test_absent_or_finished_containers_with_free_client_lock_confirm_interruption(recorded):
    run, metadata, _ = recorded
    check = observer(recorded, {"backend_matches": True, "containers": [
        {"state": "absent"}, {"state": "exited", "owned": True}, {"state": "dead", "owned": True}]})
    assert check.inspect(run, metadata)["status"] == "interrupted"
    assert check.reconcile.call_args.kwargs == {"stop": False}


def test_real_cross_process_analysis_lock_prevents_false_interruption(recorded, tmp_path):
    run, metadata, _ = recorded
    check = observer(recorded, guard=lambda: _resource_lock(tmp_path, "native", exclusive=True))
    with _resource_lock(tmp_path, "native", exclusive=False):
        result = check.inspect(run, metadata)
    assert result["status"] == "unknown" and not result["can_remove"]
    check.reconcile.assert_not_called()


def test_active_job_stays_protected_through_final_report_persistence(recorded):
    run, metadata, layout = recorded
    metadata["status"] = "succeeded"
    jobs = SimpleNamespace(active=lambda: {"active": True, "jobs": [
        {"run_id": run.name, "results_root": str(layout.runs_dir)}]})
    check = observer(recorded, jobs=jobs)
    assert not check.inspect(run, metadata)["can_remove"]
    assert not check.observe(run, metadata)["can_remove"]
    check.reconcile.assert_not_called()


def test_imported_incomplete_run_is_not_declared_inactive(recorded, tmp_path):
    run, metadata, _ = recorded
    outside = tmp_path / "other-computer" / "experiment"
    write(outside / "run.json", metadata)
    value = observer(recorded).inspect(outside, metadata)
    assert value["status"] == "unknown" and value["status_reason"] == "external"
    assert not value["can_remove"]


def test_background_observation_does_not_block_archive_and_refreshes_on_metadata_change(recorded):
    run, metadata, _ = recorded
    check = observer(recorded)
    gate, started = threading.Event(), threading.Event()
    def inspect(*args, **kwargs):
        started.set()
        assert gate.wait(5)
        return {"backend_matches": True, "containers": []}
    check.reconcile.side_effect = inspect
    first = check.observe(run, metadata)
    assert first["status"] == "unknown"
    assert started.wait(1)
    # Even with a runtime observation pending, the archive responds immediately.
    assert check.observe(run, metadata)["status"] == "unknown"
    gate.set()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        value = check.observe(run, metadata)
        if value["status"] == "interrupted":
            break
        threading.Event().wait(.005)
    assert value["status"] == "interrupted"
    metadata["status"] = "failed"
    write(run / "run.json", metadata)
    assert check.observe(run, metadata)["status"] == "failed"


def test_hidden_runs_preserve_every_input_output_and_can_be_reimported(recorded, tmp_path):
    run, metadata, layout = recorded
    source = tmp_path / "sample.bam"
    source.write_bytes(b"unaltered input")
    metadata["parameters"]["sample_mapping"] = [{"sample_id": "A", "original_path": str(source)}]
    write(run / "run.json", metadata)
    store = ResultsStore(layout.runs_dir, registry_path=tmp_path / "preferences/gui-imports.json")
    originals = {path: path.read_bytes() for path in [source, run / "run.json", run / "output/result.tsv"]}
    assert store.list_runs()["total"] == 1
    assert store.remove_run(run.name)["outputs_preserved"]
    assert store.list_runs()["total"] == 0
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert store.get_run(run.name)["id"] == run.name  # Hidden is not deletion/access revocation.
    assert store.register_run(run)["count"] == 1
    assert store.list_runs()["total"] == 1
    assert all(path.read_bytes() == content for path, content in originals.items())


def test_hidden_imported_run_is_not_reintroduced_by_listing(recorded, tmp_path):
    _, metadata, layout = recorded
    external = tmp_path / "external/example"
    write(external / "run.json", metadata)
    store = ResultsStore(layout.runs_dir)
    imported = store.register_run(external)["imported"][0]
    store.remove_run(imported)
    assert imported not in [row["id"] for row in store.list_runs()["runs"]]
    assert (external / "run.json").is_file()
    assert store.register_run(external)["imported"] == [imported]
    assert imported in [row["id"] for row in store.list_runs()["runs"]]


def test_service_removal_checks_fresh_activity_and_rejects_frontend_path(recorded, tmp_path):
    run, metadata, layout = recorded
    check = observer(recorded)
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "prefs.json"), run_observer=check)
    check.reconcile.return_value = {"backend_matches": True, "containers": [{"state": "running", "owned": True}]}
    with pytest.raises(ValidationError):
        service.call("runs.remove", {"run_id": run.name})
    assert service.call("runs.list")["total"] == 1
    with pytest.raises(ValueError):
        service.call("runs.remove", {"run_id": "../outside"})
    check.reconcile.return_value = {"backend_matches": True, "containers": [{"state": "absent"}]}
    assert service.call("runs.remove", {"run_id": run.name})["removed"]
    assert service.call("runs.list")["total"] == 0


def test_result_igv_uses_recorded_sources_and_rerun_returns_independent_draft(recorded, tmp_path):
    run, _, layout = recorded
    reference, bam = tmp_path / "reference.fa", tmp_path / "sample.bam"
    draft = {"name": "testgrafico1", "reference": str(reference), "samples": [
        {"id": "SampleA", "kind": "bam", "path": str(bam)},
        {"id": "Table", "kind": "dnp-table", "path": str(tmp_path / "table.tsv")}]}
    write(run / "gui.json", {"schema_version": 1, "name": "testgrafico1", "draft": draft})
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "prefs.json"), run_observer=observer(recorded))
    result = service.call("run.igv", {"run_id": run.name, "locus": "1:100-200"})
    assert result == {"reference": {"fasta": str(reference), "index": ""}, "tracks": [
        {"name": "SampleA", "path": str(bam)}], "locus": "1:100-200"}
    assert service.call("runs.get", {"run_id": run.name})["has_igv_inputs"]
    repeat = service.call("run.reuse", {"run_id": run.name})
    assert repeat["samples"] == draft["samples"]
    assert repeat["name"] != draft["name"]
    repeat["samples"].clear()
    assert json.loads((run / "gui.json").read_text())["draft"] == draft
    with pytest.raises(ValidationError):
        service.call("run.igv", {"run_id": run.name, "locus": "http://remote.example"})


def test_observed_interruption_is_consistent_between_run_and_unfinished_module(recorded):
    run, metadata, layout = recorded
    original = (run / "run.json").read_bytes()
    check = observer(recorded)
    store = ResultsStore(layout.runs_dir, status_observer=check.inspect)
    value = store.get_run(run.name)
    assert value["status"] == "interrupted"
    assert value["steps"][0]["status"] == "interrupted"
    assert store.overview(run.name)["modules"][0]["status"] == "interrupted"
    assert value["recorded_status"] == "running"
    assert value["status_note"] and value["can_remove"]
    assert (run / "run.json").read_bytes() == original


def test_runtime_observation_does_not_hold_global_analysis_lock(recorded):
    run, metadata, _ = recorded
    held = False
    @contextmanager
    def guard():
        nonlocal held
        held = True
        try:
            yield
        finally:
            held = False
    check = observer(recorded, guard=guard)
    def reconcile(*args, **kwargs):
        assert not held
        return {"backend_matches": True, "containers": []}
    check.reconcile.side_effect = reconcile
    assert check.inspect(run, metadata)["status"] == "interrupted"


def test_fresh_startup_record_is_not_probed_or_declared_abandoned(recorded):
    run, metadata, _ = recorded
    metadata["status"] = "preparing"
    write(run / "run.json", metadata)
    check = observer(recorded)
    result = check.observe(run, metadata)
    assert result["status"] == "unknown" and result["status_reason"] == "checking"
    assert not check._pending
    check.reconcile.assert_not_called()
