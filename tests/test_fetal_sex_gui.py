"""Maternal count tables belong to one sample in preview and archive reuse."""
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


def maternal_draft(combined=None):
    inputs = ROOT / "tests/fixtures/fetal_sex/inputs"
    roles = {key: str(inputs / f"Female_fetus_{suffix}.txt")
             for key, suffix in (("autosomes", "autosomes"), ("x", "X"), ("y", "Y"))}
    if combined is not None:
        autosomes = Path(roles["autosomes"]).read_text().splitlines()
        x = Path(roles["x"]).read_text().splitlines()
        assert x[0] == autosomes[0]
        combined.write_text("\n".join([*autosomes, *x[1:], ""]))
        roles = {"dnp": str(combined), "y": roles["y"]}
    return {"name": "Example", "caller": "tables", "samples": [],
            "fetal_sex": {"id": "Plasma", **roles}}


@pytest.mark.parametrize("combined", [False, True])
def test_preview_inherits_settings_and_reopens_original_role_files(tmp_path, combined):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    draft = maternal_draft(tmp_path / "combined.txt" if combined else None)
    prepared = prepare_analysis(draft, layout, Preferences(scientific_settings={"fetal-sex": {"a_threshold": 0.6}}))
    assert [step["workflow"] for step in prepared.preview["steps"]] == ["fetal-sex"]
    assert prepared.preview["steps"][0]["parameters"]["scientific_settings"]["a_threshold"] == 0.6
    assert Job(prepared).snapshot()["sample_count"] == 1
    assert Job(prepared).snapshot()["only_sample"] == "Plasma"
    assert {r["fetal_sex_role"]: r["original_path"] for r in prepared.preview["samples"]} == {
        key: value for key, value in draft["fetal_sex"].items() if key != "id"}
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner, scientific_settings=prepared.scientific_settings).analyze(
        caller="tables", analyses=[], run_name="fetal-reuse", **prepared.inputs)
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    reused = service.run_reuse(run.name)
    assert reused["fetal_sex"] == draft["fetal_sex"] and reused["samples"] == []
    assert prepare_analysis(reused, layout).preview["steps"] == prepared.preview["steps"]


@pytest.mark.parametrize("combined", [False, True])
def test_single_command_archive_reuses_recorded_maternal_table_roles(tmp_path, combined):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    tables = maternal_draft(tmp_path / "combined.txt" if combined else None)["fetal_sex"]
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner).fetal_sex(
        **{role: Path(path) for role, path in tables.items() if role != "id"}, run_name="standalone")
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    draft = service.run_reuse(run.name)
    assert draft["fetal_sex"] == {**tables, "id": Path(tables["dnp" if combined else "autosomes"]).stem}
    assert prepare_analysis(draft, layout).preview["steps"][0]["workflow"] == "fetal-sex"


@pytest.mark.parametrize("combined", [False, True])
def test_combined_experiment_reuses_one_maternal_table_for_both_modules(tmp_path, combined):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    panel = tmp_path / "contamination.tsv"
    panel.write_text("chr\tpos1\tpos2\nchr1\t3010000\t3010001\n")
    draft = maternal_draft(tmp_path / "combined.txt" if combined else None)
    caller_path = draft["fetal_sex"]["dnp" if combined else "autosomes"]
    draft.update(samples=[{"id": "Plasma", "kind": "dnp-table", "path": caller_path}],
                 branches={"DNP": ["contamination"]}, resources={"DNP": {"contamination_panel": str(panel)}})
    prepared = prepare_analysis(draft, layout)
    assert len(prepared.preview["samples"]) == (2 if combined else 3)
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


def test_combined_dnp_mode_requires_y_and_rejects_mixed_role_assignments(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    draft = maternal_draft(tmp_path / "combined.txt")
    draft["fetal_sex"]["y"] = ""
    with pytest.raises(ValidationError, match="Y SNP table"):
        prepare_analysis(draft, layout, language="en")
    draft["fetal_sex"]["x"] = ""
    with pytest.raises(ValidationError, match="either a combined DNP table"):
        prepare_analysis(draft, layout, language="en")


def test_bam_draft_reuses_selected_mother_in_preview_repeat_and_archive(tmp_path):
    layout = ProjectLayout(ROOT, tmp_path, tmp_path / "inputs", tmp_path / "runs", ROOT / "compose.yaml")
    reference = tmp_path / "ref.fa"
    reference.write_bytes(b">chr1\nACGT\n>chrX\nACGT\n>chrY\nACGT\n")
    reference.with_suffix(".fa.fai").write_bytes(b"chr1\t4\t6\t4\t5\nchrX\t4\t17\t4\t5\nchrY\t4\t28\t4\t5\n")
    dnp, snp = tmp_path / "dnp.tsv", tmp_path / "snp.tsv"
    dnp.write_text("chr1\t2\t3\tCG\tAT\nchrX\t2\t3\tCG\tAT\n")
    snp.write_text("chr\tpos\tref\talt\nchrY\t2\tC\tA\n")
    samples = []
    for sample_id in ("Father", "Plasma"):
        bam = tmp_path / f"{sample_id}.bam"
        bam.write_bytes(b"synthetic mount fixture")
        samples.append({"kind": "bam", "path": str(bam.resolve()), "id": sample_id})
    draft = {"name": "Maternal BAM", "caller": "both", "samples": samples, "reference": str(reference),
             "resources": {"DNP": {"panel": str(dnp.resolve())}, "SNP": {"panel": str(snp.resolve())}},
             "fetal_sex": {"source": "bam", "id": "Plasma"}}
    prepared = prepare_analysis(draft, layout)
    step = prepared.preview["steps"][-1]
    assert step["workflow"] == "fetal-sex"
    assert {ref["sample"] for ref in step["inputs"].values()} == {"Plasma"}
    assert prepared.inputs["fetal_sex"] == ("Plasma",)
    runner = DockerComposeRunner(layout, dry_run=True, transport=DockerTransport(dry_run=True))
    run = Workflows(layout, runner).analyze(caller="both", analyses=[], **prepared.inputs)
    service = GuiService(layout, preferences_store=PreferencesStore(tmp_path / "preferences.json"))
    repeated = service.run_reuse(run.name)
    assert repeated["fetal_sex"] == draft["fetal_sex"] and repeated["samples"] == samples
    assert prepare_analysis(repeated, layout).preview["steps"] == prepared.preview["steps"]
    single = service.run_prepare(run.name, "fetal-sex")
    assert single["samples"] == [samples[1]]
    dnp_step, snp_step, fetal_step = prepare_analysis(single, layout).preview["steps"]
    assert fetal_step["inputs"] == {
        "dnp": {"step": dnp_step["id"], "output": "dnp-tables", "sample": "Plasma"},
        "y": {"step": snp_step["id"], "output": "snp-tables", "sample": "Plasma"}}
    draft["fetal_sex"]["y"] = str(snp)
    with pytest.raises(ValidationError, match="maternal BAM or count tables"):
        prepare_analysis(draft, layout, language="en")
