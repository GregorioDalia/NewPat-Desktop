"""Public client entry points and compatibility with previously installed state."""
import os
from pathlib import Path
import subprocess
import sys

from newpat import __version__
from newpat.experiments.tracking import recorded_client_version
from newpat.paths import ProjectLayout


def test_canonical_and_legacy_commands_reach_the_same_client(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src"
    for module in ("newpat", "nipat"):
        result = subprocess.run([sys.executable, "-m", module, "--version"], cwd=tmp_path,
                                env={**os.environ, "PYTHONPATH": str(source)},
                                capture_output=True, check=True, text=True)
        assert result.stdout.strip() == f"NewPat {__version__}"


def test_layout_can_reopen_existing_runs_using_either_environment_prefix(tmp_path, monkeypatch):
    project = tmp_path / "app"
    project.mkdir()
    workspace = tmp_path / "existing"
    prior = workspace / "runs" / "family" / "run.json"
    prior.parent.mkdir(parents=True)
    prior.write_bytes(b'{"source":{"nipat_version":"0.9.10"}}')
    for name in ("PROJECT_DIR", "WORKSPACE_DIR", "DATA_DIR", "RUNS_DIR", "BACKEND"):
        for prefix in ("NEWPAT_", "NIPAT_"):
            monkeypatch.delenv(prefix + name, raising=False)
    monkeypatch.setenv("NIPAT_PROJECT_DIR", str(project))
    monkeypatch.setenv("NIPAT_WORKSPACE_DIR", str(workspace))
    before = ProjectLayout.discover()
    monkeypatch.setenv("NEWPAT_WORKSPACE_DIR", str(workspace))
    monkeypatch.setenv("NIPAT_WORKSPACE_DIR", str(tmp_path / "unused"))
    monkeypatch.setenv("NEWPAT_PROJECT_DIR", str(project))
    after = ProjectLayout.discover()
    assert before == after and (after.runs_dir / "family/run.json").samefile(prior)
    assert recorded_client_version({"nipat_version": "0.9.10"}) == "0.9.10"
    assert recorded_client_version({"newpat_version": __version__}) == __version__
