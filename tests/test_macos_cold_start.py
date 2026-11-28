"""Dedicated-Mac qualification must launch science directly after a verified stop."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from newpat.cli import build_parser


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("scenario, error", [
    ("idle", None),
    ("busy", "busy"),
    ("never-stopped", "verify.*stopped"),
    ("altered-results", "altered results"),
])
def test_cold_start_runs_science_with_default_settings(tmp_path, monkeypatch, scenario, error):
    spec = importlib.util.spec_from_file_location("verify_macos_runtime_fixture", ROOT / "scripts/verify_macos_runtime.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    monkeypatch.syspath_prepend(str(ROOT / "scripts/acceptance"))
    import installed_workflows

    image = "sha256:" + "b" * 64
    prior = tmp_path / "self-tests/example/output/SNPcall_output.txt"
    prior.parent.mkdir(parents=True)
    prior.write_text("previous result")
    runtime = Mock()
    runtime._instance_info.return_value = {"status": "Running" if scenario == "never-stopped" else "Stopped"}
    monkeypatch.setattr(verifier.subprocess, "check_output",
                        lambda *a, **kw: "another-container" if scenario == "busy" else "")
    oracle = Mock(return_value={"CPI_full": 8})
    monkeypatch.setattr(installed_workflows, "check_positive_cpi", oracle)
    steps = []

    def execute(name, args, timeout):
        steps.append(name)
        if name == "cold-stop":
            assert args == ["--runtime", "stop"]
            return
        assert name == "cold-start" and steps == ["cold-stop", "cold-start"]
        options = build_parser().parse_args(args)
        assert options.preset == "dnp-cpi"
        assert options.pair[0][0] == "family_a"
        assert all(Path(p).is_file() for p in options.pair[0][1:])
        assert options.execution_mode is None and options.performance_diagnostics is None
        run = options.runs_dir / options.run_name
        run.mkdir()
        (run / "run.json").write_text(json.dumps({
            "run_id": "new", "status": "succeeded", "engine_verification": "verified",
            "runtime": {"image_id": image}, "commands": [{"status": "succeeded"}],
            "execution_options": {"execution_mode": "auto", "performance_diagnostics": False},
        }))
        if scenario == "altered-results":
            prior.write_text("replaced")

    if error:
        with pytest.raises(ValueError, match=error):
            verifier.check_cold_start(execute, runtime, ROOT, tmp_path, image)
    else:
        result = verifier.check_cold_start(execute, runtime, ROOT, tmp_path, image)
        assert result["CPI_full"] == 8 and result["run_id"] == "new"
        oracle.assert_called_once_with(tmp_path / "dnp-cpi-after-stop", contamination=False, snp=False, cutoffs=False)
    if scenario in {"busy", "never-stopped"}:
        assert steps == ([] if scenario == "busy" else ["cold-stop"])
        oracle.assert_not_called()
