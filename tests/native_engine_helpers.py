"""Run the installed scientific engine entry point on a synthetic request."""

import json
import os
import subprocess
import sys

from test_native_r_edge_cases import HELPERS, PAYLOAD


def execute_workflow(workflow, root, *, env=None, execution_mode="serial", timeout=90, **fields):
    root.mkdir()
    request = root / "request.json"
    request.write_text(json.dumps({
        "schema_version": 1, "workflow": workflow, **fields,
        "work_dir": str(root / "work"), "out_dir": str(root / "output"),
    }), encoding="utf-8")
    environment = dict(os.environ if env is None else env,
                       PYTHONPATH=str(HELPERS.parent), NEWPAT_EXECUTION_MODE=execution_mode,
                       NEWPAT_DNP_BLOCKS_HELPER=str(HELPERS / "dnp_blocks.R"),
                       NEWPAT_DNP_PILEUP_HELPER=str(HELPERS / "dnp_pileup.py"),
                       NEWPAT_PARALLEL_HELPER=str(HELPERS / "parallel.R"),
                       NEWPAT_SETTINGS_HELPER=str(HELPERS / "settings.R"),
                       NEWPAT_SETTINGS_REGISTRY=str(HELPERS / "settings_data.json"),
                       NEWPAT_PLOTS_HELPER=str(HELPERS / "plots.R"))
    environment.pop("NEWPAT_SCIENTIFIC_SETTINGS", None)
    return subprocess.run(
        [sys.executable, str(PAYLOAD / "engine/main.py"), "execute", workflow,
         "--request", str(request)], cwd=root, env=environment,
        capture_output=True, text=True, timeout=timeout,
    )
