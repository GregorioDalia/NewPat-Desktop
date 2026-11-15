"""Bundled IGV provenance and local-only adapter behavior."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "src" / "nipat" / "gui" / "web"


def test_igv_assets_are_pinned_and_complete():
    vendor = WEB / "vendor"
    manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "3.8.9"
    assert manifest["license"] == "MIT"
    assert "igv.min.js" in manifest["assets"]
    assert "igv.LICENSE.txt" in manifest["assets"]
    assert len(manifest["assets"]) >= 10
    for name, expected in manifest["assets"].items():
        path = vendor / name
        assert path.resolve().is_relative_to(vendor.resolve())
        content = path.read_bytes()
        assert len(content) == expected["bytes"]
        assert hashlib.sha256(content).hexdigest() == expected["sha256"]
    assert "Permission is hereby granted" in (vendor / "igv.LICENSE.txt").read_text()


def test_igv_adapter_local_resources_and_lifecycle():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the GUI JavaScript contract checks")
    result = subprocess.run(
        [node, str(ROOT / "tests" / "test_gui_igv_adapter.cjs"), str(WEB / "igv-view.js")],
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "passed" in result.stdout
