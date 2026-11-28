"""Focused native-R CPIN regression checks with independently derived numbers."""

import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from newpat_scientific.settings import settings_context
from native_r_helpers import NATIVE_R_AVAILABLE, NATIVE_R_REASON

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/cpin"
sys.path.insert(0, str(ROOT / "scripts"))
from verify_cpin_update import check_outputs

pytestmark = pytest.mark.skipif(not NATIVE_R_AVAILABLE, reason=NATIVE_R_REASON)


def table(path):
    with path.open() as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def run_native(tmp_path, marker="SNP", settings=None, inputs=None, trios="M1:F1:C1", native_options=()):
    run = tmp_path / "run"
    work = run / "work"
    work.mkdir(parents=True)
    inputs = inputs or FIXTURE / marker
    env = os.environ.copy()
    env.update(NEWPAT_EXECUTION_MODE="serial",
               NEWPAT_PARALLEL_HELPER=str(ROOT / "src/newpat_scientific/parallel.R"),
               NEWPAT_PLOTS_HELPER=str(ROOT / "src/newpat_scientific/plots.R"))
    with settings_context("cpin", settings or {}, work):
        for name in ("NEWPAT_SCIENTIFIC_SETTINGS", "NEWPAT_SETTINGS_HELPER", "NEWPAT_SETTINGS_REGISTRY"):
            env[name] = os.environ[name]
        result = subprocess.run([
            "Rscript", str(ROOT / "scientific/vendor/NEWPAT/CPI_postnatal/Postnatal_CPI.R"),
            "--pileup_dir", str(inputs), "--out_dir", str(run / "output"),
            "--trios", trios, "--mother_prefix", "Mother", "--father_prefix", "Father",
            "--child_prefix", "Child", "--popfreq", str(inputs / "population.txt"),
            *native_options,
        ], env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    return run


@pytest.mark.parametrize("marker", ["SNP", "DNP"])
def test_analytical_sites_and_scalar_outputs(tmp_path, marker):
    check_outputs(run_native(tmp_path, marker), marker)


def test_native_role_local_ids_use_distinct_prefixed_files(tmp_path):
    inputs = tmp_path / "inputs"
    shutil.copytree(FIXTURE / "SNP", inputs)
    for role, identifier in (("Mother", "M1"), ("Father", "F1"), ("Child", "C1")):
        (inputs / f"{role}{identifier}.txt").rename(inputs / f"{role}A.txt")
    run = run_native(tmp_path, inputs=inputs, trios="A:A:A")
    rows = table(run / "output/Summary_Postnatal_CPI.txt")
    assert {row["Trio"] for row in rows} == {"MotherA-FatherA-ChildA_SNPs"}
    assert len(rows) == 1
    assert float(rows[0]["CPI"]) == pytest.approx(1.25 * (.001 / .4) ** 2 / .6)


def test_native_sidecar_records_explicit_cli_overrides(tmp_path):
    run = run_native(tmp_path, native_options=("--min_coverage", "3", "--mismatch_probability_snp", "0.02"))
    document = json.loads((run / "output/scientific-settings.json").read_text())
    assert document["parameters"]["min_coverage"] == 3
    assert document["parameters"]["mismatch_probability_snp"] == 0.02
    assert document["workflow"] == "cpin"
    assert document["constants"]["ploidy"]["value"] == 2
