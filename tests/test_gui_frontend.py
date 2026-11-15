"""Run the production frontend state/RPC scenarios in the standard test gate."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_state_and_rpc_scenarios():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the GUI JavaScript contract checks")
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, str(project / "scripts/test_gui_frontend.cjs")],
                            cwd=project, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout.strip())
    assert evidence["status"] == "passed"
    assert evidence["assertions"] > 0 and evidence["rpcCalls"] > 0
    print(result.stdout.strip())
