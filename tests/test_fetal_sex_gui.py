"""The three maternal caller tables belong to one sample in preview and archive reuse."""
from copy import deepcopy
from pathlib import Path

import pytest

from nipat.errors import ValidationError
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.transport import DockerTransport
from nipat.execution.workflows import Workflows
from nipat.gui.jobs import Job
from nipat.gui.plan import prepare_analysis
from nipat.gui.service import GuiService
from nipat.paths import ProjectLayout
from nipat.preferences import Preferences, PreferencesStore

ROOT = Path(__file__).resolve().parents[1]


def maternal_draft():
    inputs = ROOT / "tests/fixtures/fetal_sex/inputs"
    roles = {key: str(inputs / f"Female_fetus_{suffix}.txt")
             for key, suffix in (("autosomes", "autosomes"), ("x", "X"), ("y", "Y"))}
    return {"name": "Example", "caller": "tables", "samples": [],
            "fetal_sex": {"id": "Plasma", **roles}}


def test_standalone_preview_inherits_settings_and_reopens_all_three_roles(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    draft = maternal_draft()
    prepared = prepare_analysis(draft, layout, Preferences(scientific_settings={"fetal-sex": {"a_threshold": 0.6}}))
    assert [step["workflow"] for step in prepared.preview["steps"]] == ["fetal-sex"]
    assert prepared.preview["steps"][0]["parameters"]["scientific_settings"]["a_threshold"] == 0.6
    assert Job(prepared).snapshot()["sample_count"] == 1
    assert Job(prepared).snapshot()["only_sample"] == "Plasma"
    assert {r["fetal_sex_role"]: r["original_path"] for r in prepared.preview["samples"]} == {
        key: draft["fetal_sex"][key] for key in ("autosomes", "x", "y")}
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner, scientific_settings=prepared.scientific_settings).analyze(
        caller="tables", analyses=[], run_name="fetal-reuse", **prepared.inputs)
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    reused = service.run_reuse(run.name)
    assert reused["fetal_sex"] == draft["fetal_sex"] and reused["samples"] == []
    assert prepare_analysis(reused, layout).preview["steps"] == prepared.preview["steps"]


def test_single_command_archive_reuses_recorded_maternal_table_roles(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    tables = maternal_draft()["fetal_sex"]
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner).fetal_sex(
        **{role: Path(tables[role]) for role in ("autosomes", "x", "y")}, run_name="standalone")
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    draft = service.run_reuse(run.name)
    assert draft["fetal_sex"] == {**tables, "id": Path(tables["autosomes"]).stem}
    assert prepare_analysis(draft, layout).preview["steps"][0]["workflow"] == "fetal-sex"


def test_combined_experiment_reuses_one_maternal_table_for_both_modules(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    panel = tmp_path / "contamination.tsv"
    panel.write_text("chr\tpos1\tpos2\nchr1\t3010000\t3010001\n")
    draft = maternal_draft()
    draft.update(samples=[{"id": "Plasma", "kind": "dnp-table", "path": draft["fetal_sex"]["autosomes"]}],
                 branches={"DNP": ["contamination"]}, resources={"DNP": {"contamination_panel": str(panel)}})
    prepared = prepare_analysis(draft, layout)
    assert len(prepared.preview["samples"]) == 3
    assert Job(prepared).snapshot()["sample_count"] == 1
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner).analyze(caller="tables", analyses=[], **prepared.inputs)
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    restored = service.run_reuse(run.name)
    assert restored["samples"] == draft["samples"] and restored["fetal_sex"] == draft["fetal_sex"]
    assert [step["workflow"] for step in prepare_analysis(restored, layout).preview["steps"]] == [
        "contamination", "fetal-sex"]


def test_role_files_required_and_checked_again_before_start(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    draft = maternal_draft()
    incomplete = deepcopy(draft)
    del incomplete["fetal_sex"]["x"]
    with pytest.raises(ValidationError, match="DNP autosomici"):
        prepare_analysis(incomplete, layout)
    changed = tmp_path / "Autosomes.txt"
    changed.write_bytes(Path(draft["fetal_sex"]["autosomes"]).read_bytes())
    draft["fetal_sex"]["autosomes"] = str(changed)
    prepared = prepare_analysis(draft, layout)
    changed.write_text("modified")
    with pytest.raises(ValidationError, match="cambiato"):
        prepared.assert_inputs_unchanged()
