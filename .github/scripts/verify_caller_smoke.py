"""Exercise one desktop BAM-to-DNP/SNP workflow against the published synthetic trio."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TRIO = ROOT / "examples/synthetic-trio"
GENOTYPES = {"mother": "0/0", "father": "0/1", "child": "0/1"}

sys.path.insert(0, str(ROOT / "src"))
from nipat.execution.runner import DockerComposeRunner
from nipat.execution.workflows import Workflows
from nipat.gui.plan import prepare_analysis
from nipat.paths import ProjectLayout


def read_table(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def check_table(path: Path, marker: str, sample: str) -> None:
    # The example count tables are inputs shipped for downstream-only analyses.
    # They were produced independently of this run and can also be read back from BAM.
    expected = read_table(TRIO / "counts" / marker / f"{sample}.txt")
    for row in expected:
        row["GT"] = GENOTYPES[sample]
    fields = ["chr", *(["pos1", "pos2"] if marker == "dnp" else ["pos"]),
              "REF", "ALT", "N_REF", "N_ALT", "N_Other", "total_count", "GT"]

    def rows(records):
        return Counter(tuple(row[field] for field in fields) for row in records)

    wanted, actual = rows(expected), rows(read_table(path))
    if len(expected) != 3 or actual != wanted:
        raise ValueError(f"{marker.upper()} {sample}: expected three matching loci. "
                         f"Missing {dict(wanted - actual)}, unexpected {dict(actual - wanted)}")


def check_results(workflow: Path) -> None:
    state = json.loads((workflow / "workflow-state.json").read_text(encoding="utf-8"))
    steps = state["steps"]
    if (state["status"] != "succeeded" or any(step["status"] != "succeeded" for step in steps)
            or Counter(step["workflow"] for step in steps) != {"dnp-call": 1, "snp-call": 3}):
        raise ValueError("Expected one successful DNP step and three successful SNP steps")
    samples = []
    for step in steps:
        marker = step["workflow"].removesuffix("-call")
        for artifact in step["artifacts"][f"{marker}-tables"]:
            sample = artifact["sample"]
            check_table(workflow / artifact["path"], marker, sample)
            samples.append((marker, sample))
    if Counter(samples) != Counter((marker, sample) for marker in ("dnp", "snp") for sample in GENOTYPES):
        raise ValueError(f"Expected one DNP and one SNP table per sample, got {samples}")


def prepare(layout: ProjectLayout):
    draft = {
        "name": "Synthetic caller smoke", "caller": "both",
        "samples": [{"id": sample, "kind": "bam", "path": str(TRIO / f"alignments/{sample}.bam")}
                    for sample in GENOTYPES],
        "reference": str(TRIO / "reference/synthetic.fa"),
        "resources": {marker.upper(): {"panel": str(TRIO / f"panels/{marker}.tsv")}
                      for marker in ("dnp", "snp")},
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
        prepared.assert_inputs_unchanged()
        runner = DockerComposeRunner(layout, options=prepared.execution)
        run = Workflows(layout, runner, prepared.scientific_settings).analyze(
            caller=prepared.draft["caller"], analyses=[], run_name="caller-smoke", **prepared.inputs)
        check_results(run / "output/workflow")
        print("Synthetic trio passed: both callers matched counts and genotypes at all 18 sample-loci.")


if __name__ == "__main__":
    main()
