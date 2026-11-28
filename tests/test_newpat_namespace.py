"""An isolated client uses only its own entry point and settings."""
import os
from pathlib import Path
import subprocess
import sys

from newpat import __version__
from newpat.experiments.tracking import recorded_client_version
from newpat.paths import ProjectLayout


def test_only_newpat_cli_is_distributed(tmp_path):
    project = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(project / "src")}
    result = subprocess.run([sys.executable, "-m", "newpat", "--version"], cwd=tmp_path,
                            env=env, capture_output=True, check=True, text=True)
    assert result.stdout.strip() == f"NewPat {__version__}"
    assert not (project / "src/nipat.py").exists()
    assert not (project / "nipat.cmd").exists()


def test_old_environment_does_not_select_or_create_a_workspace(tmp_path, monkeypatch):
    for name in ("WORKSPACE_DIR", "RUNS_DIR", "DATA_DIR", "BACKEND"):
        monkeypatch.delenv("NEWPAT_" + name, raising=False)
    monkeypatch.setenv("NEWPAT_PROJECT_DIR", str(tmp_path / "app"))
    old_workspace = tmp_path / "historical"
    monkeypatch.setenv("NIPAT_WORKSPACE_DIR", str(old_workspace))
    assert ProjectLayout.discover().workspace_dir == tmp_path
    monkeypatch.setenv("NEWPAT_WORKSPACE_DIR", str(tmp_path / "workspace"))
    layout = ProjectLayout.discover()
    layout.ensure_storage_dirs()
    assert layout.runs_dir == tmp_path / "workspace" / "runs"
    assert not old_workspace.exists()
    assert recorded_client_version({"nipat_version": "0.9.10"}) is None
    assert recorded_client_version({"newpat_version": __version__}) == __version__
