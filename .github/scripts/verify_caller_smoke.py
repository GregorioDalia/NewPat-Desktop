"""Verify the desktop caller workflow and genotype edge cases on synthetic data."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TRIO = ROOT / "examples/synthetic-trio"
ORACLE = ROOT / "tests/fixtures/synthetic-trio-v1"
SAMPLES = ("mother", "father", "child")
MARKERS = ("dnp", "snp")
VALUE_FIELDS = ("REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count", "GT")

sys.path.insert(0, str(ROOT / "src"))
from newpat.experiments.runner import DockerComposeRunner
from newpat.experiments.workflows import Workflows
from newpat.desktop.plan import prepare_analysis
from newpat.paths import ProjectLayout
from verify_caller_edges import verify_edges


def read_table(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def check_inputs(prepared) -> None:
    expected = {}
    for line in (ORACLE / "inputs.sha256").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ")
        if name in expected:
            raise ValueError(f"Duplicate input in the trio oracle: {name}")
        expected[name] = digest

    # Desktop preparation resolves inputs, including system aliases for the temp directory.
    trio_root = TRIO.resolve(strict=True)
    inputs = prepared.inputs
    roles = {f"alignments/{sample}.bam": path for sample, path in inputs["samples"]}
    roles["reference/synthetic.fa"] = inputs["reference"]
    for marker in MARKERS:
        roles[f"panels/{marker}.tsv"] = inputs[f"{marker}_panel"]
    if any(path != trio_root / relative for relative, path in roles.items()):
        raise ValueError("A trio input was assigned to the wrong sample, panel or reference")
    if [sample for sample, path in inputs["samples"]] != list(SAMPLES):
        raise ValueError("The trio plan changed sample identity or order")

    # Plan evidence includes the FASTA and BAM indexes actually discovered by the desktop.
    discovered = {path.relative_to(trio_root).as_posix(): path for path, _ in prepared.evidence}
    if discovered.keys() != expected.keys():
        raise ValueError("The desktop plan did not select the pinned trio inputs and indexes")
    for name, path in discovered.items():
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != expected[name]:
                raise ValueError(f"Synthetic trio input changed: {name}")


def check_table(path: Path, marker: str, sample: str, expected: list[dict]) -> None:
    coordinates = ("chr", "pos1", "pos2") if marker == "dnp" else ("chr", "pos")
    fields = (*coordinates, *VALUE_FIELDS)
    wanted = Counter(tuple(row["pos" if field == "pos1" else field] for field in fields)
                     for row in expected if row["marker"] == marker and row["sample"] == sample)
    actual = Counter(tuple(row[field] for field in fields) for row in read_table(path))
    if len(wanted) != 3 or wanted.total() != 3 or actual != wanted:
        raise ValueError(f"{marker.upper()} {sample}: expected three matching loci. "
                         f"Missing {dict(wanted - actual)}, unexpected {dict(actual - wanted)}")


def check_results(workflow: Path) -> None:
    state = json.loads((workflow / "workflow-state.json").read_text(encoding="utf-8"))
    steps = state["steps"]
    if (state["status"] != "succeeded" or any(step["status"] != "succeeded" for step in steps)
            or Counter(step["workflow"] for step in steps) != {"dnp-call": 1, "snp-call": 3}):
        raise ValueError("Expected one successful DNP step and three successful SNP steps")
    expected = read_table(ORACLE / "expected.tsv")
    if len(expected) != len(MARKERS) * len(SAMPLES) * 3:
        raise ValueError("The trio oracle must specify all 18 sample-loci")
    samples = []
    seen_paths = set()
    for step in steps:
        marker = step["workflow"].removesuffix("-call")
        for artifact in step["artifacts"][f"{marker}-tables"]:
            sample = artifact["sample"]
            path = (workflow / artifact["path"]).resolve()
            if not path.is_relative_to(workflow.resolve()) or path in seen_paths:
                raise ValueError("Each sample must have its own table in the workflow output")
            seen_paths.add(path)
            check_table(path, marker, sample, expected)
            samples.append((marker, sample))
    if Counter(samples) != Counter((marker, sample) for marker in MARKERS for sample in SAMPLES):
        raise ValueError(f"Expected one DNP and one SNP table per sample, got {samples}")


def prepare(layout: ProjectLayout):
    draft = {
        "name": "Synthetic caller smoke", "caller": "both",
        "samples": [{"id": sample, "kind": "bam", "path": str(TRIO / f"alignments/{sample}.bam")}
                    for sample in SAMPLES],
        "reference": str(TRIO / "reference/synthetic.fa"),
        "resources": {marker.upper(): {"panel": str(TRIO / f"panels/{marker}.tsv")}
                      for marker in MARKERS},
        "execution": {"max_workers": 2},
    }
    return prepare_analysis(draft, layout, language="en")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Locally loaded scientific runtime image")
    args = parser.parse_args()
    os.environ.update(NIPAT_RUNTIME_IMAGE=args.image, NIPAT_BACKEND="native")
    with tempfile.TemporaryDirectory(prefix="newpat-caller-smoke-") as directory:
        root = Path(directory)
        layout = ProjectLayout(ROOT, root, root / "data", root / "runs", ROOT / "compose.yaml")
        prepared = prepare(layout)
        check_inputs(prepared)
        prepared.assert_inputs_unchanged()
        runner = DockerComposeRunner(layout, options=prepared.execution)
        run = Workflows(layout, runner, prepared.scientific_settings).analyze(
            caller=prepared.draft["caller"], analyses=[], run_name="caller-smoke", **prepared.inputs)
        check_inputs(prepared)
        check_results(run / "output/workflow")
        print("Synthetic trio passed: both callers matched counts and genotypes at all 18 sample-loci.")
        verify_edges(args.image, root / "caller-edges")
        print("Genotype edge cases passed: 3 DNP loci including 1/1, and 2 SNP loci with GT=NA.")


if __name__ == "__main__":
    main()
